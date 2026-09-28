# Research: Contabilidad Habitual, Informes y Cierre de Ejercicio (SPEC-004)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Resoluciones de los unknowns del Technical Context y decisiones de diseño conforme a la constitución y al plan raíz.

## D1. Balance de Sumas y Saldos: fuente y garantía de cuadre

- **Decision**: El Balance agrega `journal_entry_line` (solo asientos del diario con efecto en el ejercicio: `POSTED` y `CANCELLED` que ya se compensan con su REVERSAL) de la empresa activa, uniendo `account_plan` por `(empresa_id, account_id)`, filtrando por rango de fechas (por `fecha` del asiento). Las sumas y saldos por cuenta se calculan con `SUM(NUMERIC(18,4))` y `Decimal` en la presentación.
- **Rationale**: FR-002/FR-003: el cuadre (Sum Debe == Sum Haber) es consecuencia directa de la partida doble estricta del motor (SPEC-002); SC-001 exige cuadre en el 100 % de las generaciones.
- **Alternatives considered**: Tabla materializada de saldos (rápida pero desincronizable con el diario inmutable); totalizar en el frontend (descarta precisión y autoridad del backend).

## D2. Agregación por nivel de profundidad del plan

- **Decision**: El parámetro `level` indica el nivel de cuentas a mostrar. La agregación a un nivel N **agrupa por los primeros N dígitos del código** (columna `code` de `account_plan`) dentro de la empresa activa: si el plan tiene nivel inferior al solicitado, se agrega **al mayor nivel disponible** sin error (edge case); cada fila `{ codigo, nombre, nivel, suma_debe, suma_haber, saldo_deudor/acreedor }`.
- **Rationale**: El nivel en `account_plan` se deriva de la longitud del código (SPEC-001); agrupar por prefijo de código es la forma natural de roll-up de hojas a cuentas de cargo (4300 → 430 → 43).
- **Alternatives considered**: Recursivo padre-hijo por `parent_id` (más lento y frágil con varias ramas); nivel fijo = plan (falla la petición de mayor nivel); devolver error si se pide nivel 6+ (edge case de la spec exige agregar al máximo disponible).

## D3. Libro Mayor por subcuenta

- **Decision**: Endpoint de mayor por `account_id` de la empresa activa: devuelve movimientos cronológicos `(fecha, numero, concepto, debe, haber, saldo_acumulado)` de asientos con efecto, ordenados por `(fecha, numero)` y con **saldo acumulado exacto** en `Decimal`. Si la subcuenta no tiene movimientos → lista vacía sin error (edge case).
- **Rationale**: FR-004/SC-003 (trazabilidad por cuenta); el saldo acumulado es el invariante de reconciliación (MUST ser exacto).
- **Alternatives considered**: Calcular el saldo con `float` en bucle (prohibido); saldo inicial agregado + saldo final sin detalle (pierde el carácter cronológico del Mayor).

## D4. Ejercicios contables con bloqueo `is_closed`

- **Decision**: `fiscal_year` provisionado (alta/gestión **fuera de alcance**; solo se consulta y se bloquea). Guarda en el motor de asientos (SPEC-002): si la fecha del asiento no cae en ningún ejercicio de la empresa → HTTP 400; si el ejercicio está `is_closed` → HTTP 400 y ninguna escritura entra en el periodo (FR-007/SC-002). No se crean ejercicios automáticamente.
- **Rationale**: El cierre inmoviliza el periodo cumpliendo la inmutabilidad (constitución II); la spec fija el rechazo F-400 y la no-creación automática.
- **Alternatives considered**: Bloqueo por rango de fechas sin tabla de ejercicios (duplica lógica y la hace inconsistente); permitir escrituras en cerrado (corrompe cierres y reportes).

## D5. Atomicidad del cierre de ejercicio

- **Decision**: `POST /fiscal-years/{year}/close` abre una **única transacción** (`async with async_session.begin()`) que: (1) **bloquea el año** con `SELECT ... FOR UPDATE` del `fiscal_year`; (2) valida estado abierto y sin asientos en borrador pendientes; (3) crea el **asiento de regularización** (saldar grupos 6 y 7 contra `129` Resultado del ejercicio) balanceado; (4) crea el **asiento de cierre** (saldar las cuentas de balance/patrimoniales) balanceado; (5) marca `is_closed = True` y guarda los ids de los asientos generados; todo con auditoría. Cualquier fallo revierte el conjunto (FR-008/SC-004). Un segundo cierre concomitante falla por el lock (409).
- **Rationale**: Constitución (operaciones atómicas; bloqueo + inmutabilidad); SC-004 exige "juntos o ninguno" en el 100 % de las ejecuciones.
- **Alternatives considered**: Cierre en pasos separados (deja un ejercicio a medio cerrar); sin `FOR UPDATE` (dos cierres concurrentes → duplicados); cierre que admite borradores (viola la consolidación).

## D6. Asientos de regularización y cierre (cuentas PGC)

- **Decision**: **Regularización**: las cuentas de los grupos 6 y 7 (compras/gastos e ingresos) se saldan contra la cuenta de resultado (`129`, saldo de la empresa en el ejercicio) → asiento balanceado auto-generado. **Cierre**: las cuentas con saldo (activo/pasivo/patrimonio) se saldan entre sí dejando el balance a cero, generando el saldo de apertura del ejercicio siguiente. Ambos asientos quedan `POSTED` e inmutables (FR-010).
- **Rationale**: Es el tratamiento PGC estándar del cierre; las cuentas `129` y la identificación de cuentas patrimoniales derivan del plan (SPEC-001) por nivel/código.
- **Alternatives considered**: Regularización manual por el contador (error-prone y rompe atomicidad); omitir el asiento de cierre (deja el balance sin saldar → descuadre del ejercicio siguiente).

## D7. Precisión decimal en consolidaciones y saldos

- **Decision**: Toda agregación (`SUM`, `saldo_acumulado`, `saldo_deudor/acreedor`, totales del Balance) opera sobre columnas `NUMERIC(18,4)` con `Decimal` en el backend; los formatos de presentación conservan 4 decimales. Prohibido `float` (FR-005/SC-005).
- **Rationale**: La aritmética del dominio prohíbe coma flotante; los informes heredan la precisión canónica del motor (SPEC-002 D7).
- **Alternatives considered**: Redondeo en el frontend (descarta precisión del backend); agregación con tipos de coma flotante (prohibido).

## D8. Facturas: entidad con precisión y numeración correlativa

- **Decision**: Modelo `invoice` (emitida/recibida) con `base`, `cuota_iva`, `total` en `NUMERIC(18,4)`, `CHECK (total = base + cuota_iva)` y **número correlativo por (empresa, ejercicio)** asignado atómicamente con el patrón de secuencia bloqueada de SPEC-002 (`UNIQUE (empresa_id, ejercicio, numero_seq)`). En esta feature **solo se define y persiste la entidad a través de un servicio** (`invoice_service`) y sus pruebas; los endpoints de gestión se difieren (assumption de la spec).
- **Rationale**: FR-005/FR-006 (precisión exacta + correlatividad de la constitución IV); la spec excluye la API de gestión de esta feature, pero exige persistir correctamente.
- **Alternatives considered**: Endpoints CRUD completos (fuera del alcance fijado); número global por empresa sin ejercicio (rompe la correlatividad por ejercicio); total como columna sin CHECK (permite facturas descuadradas).

## D9. Inmutabilidad y protección de facturas

- **Decision**: Sin `DELETE`; la factura vinculada a un asiento es **inmutable** (puede consultarse e imprimirse); los campos de contexto (NIF tercero, fechas) solo se corrigen antes del vínculo con el asiento. El vínculo `asiento_id` es opcional y una vez fijado no cambia.
- **Rationale**: Las facturas son documento soporte (constitución II, inmutabilidad del soporte contable); la integridad de base/IVA/total está garantizada por el CHECK.
- **Alternatives considered**: Edición libre (corrompe conciliaciones y registros fiscales); borrado físico (pierde trazabilidad).

## D10. Auditoría de cierre y facturas

- **Decision**: El cierre de ejercicio, la creación de facturas y la generación de asientos de cierre escriben `audit_log` (empresa_id, actor, acción `CLOSE_YEAR`/`CREATE_INVOICE`/`REGULARIZATION`/`CLOSING_ENTRY`, IP, payload JSONB con importes como cadenas Decimal) **dentro de la misma transacción**.
- **Rationale**: Constitución (auditoría inmutable, misma transacción ACID); el cierre queda trazable y no reabrible (SC-004).
- **Alternatives considered**: Auditoría asíncrona (pierde atomicidad crítica del cierre); payload con importes flotantes (prohibido).

## D11. Informes con datos de otras empresas: aislamiento

- **Decision**: Todas las consultas de informes, ejercicios y facturas filtran por `empresa_id` derivado de la sesión; un intento de informes/mayor/cierre sobre datos de otra empresa → 404/403 sin exponer información.
- **Rationale**: Constitución III (aislamiento en el 100 % de las operaciones de datos); FR-001.
- **Alternatives considered**: Consultas que ignoran el tenant (prohibido); parámetros de empresa en el query (datos no confiables).

## D12. Stack e integración

- **Decision**: Backend **FastAPI async + SQLAlchemy 2.x async + asyncpg** en `services/reports`, `services/closing`, `services/invoicing`; informes como servicios de **lectura puros** (sin escritura, salvo el cierre que usa `async with async_session.begin()`); frontend Next.js con páginas de informes y cierre.
- **Rationale**: Coherencia con la constitución y el plan raíz; separación lectura/escritura facilita autorización y rendimiento.
- **Alternatives considered**: Materializar informes en tablas (desincronización); ejecutar el cierre fuera del bloque transaccional (rompe FR-008).