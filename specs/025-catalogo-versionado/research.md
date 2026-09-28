# Research: Catálogo Versionado del Plan de Cuentas (SPEC-025)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Resoluciones de los unknowns del Technical Context y decisiones de diseño conforme a la constitución y al `plan.md` raíz (SPEC-001).

## D1. Estrategia de versionado: snapshot completo vs deltas con estado

- **Decision**: el versionado es **aditivo sobre `account_plan`** (SPEC-001). `account_plan` conserva la vida histórica de cada cuenta (altas/renombrados/inactivas nunca se borran — constitución II). La versión del catálogo se modela con una **cabecera `CatalogoVersion`** (código, vigencia, estado) y una **proyección `CatalogoCuenta`** que registra, por versión, la membresía y el estado de cada cuenta (`igual`, `nueva`, `renombrada`, `suprimida`). No se clonan filas de `account_plan`; se referencian por `(empresa_id, account_id)`.
- **Rationale**: evita la duplicación masiva del plan (mil+ filas por versión), preserva la unicidad canónica `UNIQUE (tenant_id, code)` de SPEC-001, y mantiene la inmutabilidad histórica: una cuenta suprimida en la versión 2 sigue existiendo en `account_plan` y es visible en el contexto de la versión 1 (US1/edge cases). La resolución de la vigencia es un lookup de cabecera + unión sobre membresía, indexado por `(empresa_id, account_id)` en `CatalogoCuenta`.
- **Alternatives considered**: (a) snapshot: clonar el árbol completo por versión (simple, pero multiplica el almacenamiento y rompe la unicidad canónica de código dentro de la empresa); (b) columnas de vigencia en cada fila de `account_plan` (mezcla el catálogo canónico con el histórico y complica los triggers de SPEC-001); (c) ramas tipo tabla `account_plan_version` con el propio `code` repetido por versión (usado por algunos ERPs, pero complejo de conciliar con los triggers `is_selectable`/protección del plan raíz).

## D2. Resolución histórica: versión vigente en la fecha del asiento

- **Decision**: un asiento se resuelve con la versión **cuyo `fecha_inicio <= fecha_asiento <= fecha_fin`** (o `fecha_fin NULL` = vigente sin fin) dentro de la empresa activa. Si ninguna versión cubre la fecha (p. ej. anterior a la primera versión) se resuelve contra la primera versión creada con `fecha_inicio` más antigua, documentada como fallback explícito (nunca silencioso). El servicio `resolucion_historica.py` expone `resolver_version(fecha)` y `obtener_cuenta_vigente(empresa, fecha, account_id)` usados por el motor de asientos (SPEC-002) y por la UI de "cuenta vigente en fecha".
- **Rationale**: cumple SC-001 (100 % de asientos resuelven con la versión de su fecha) y FR-003; la resolución es determinista y testeable; el fallback es trazable en el log de auditoría cuando se usa.
- **Alternatives considered**: (a) resolución por ejercicio declarado en cabecera del asiento (frágil: la fecha y el ejercicio pueden no coincidir); (b) resolución en frontend (descarta la garantía constitucional de backend); (c) devolver error si no hay versión cubriente (rompe asientos históricos previos a la primera versión).

## D3. Formato de importación normativa

- **Decision**: fichero estructurado **CSV o JSON** (`application/json` o `text/csv`) con las operaciones: `alta` (código, nombre, cuenta padre, nivel), `renombrado` (código origen → código destino y/o nombre), `baja` (código). El fichero puede incluir un bloque de **mapeo explícito** `origen → destino(s)` (también aceptado como objeto JSON independiente). La validación (Pydantic v2) ocurre en el backend; los errores devuelven 422 con la lista de filas rechazadas por tipo.
- **Rationale**: es el formato interoperable asumido por la spec (Assumptions: "formato estructurado (CSV/JSON) con el mapeo"); permite importación masiva y trazable con payload de auditoría; la validación en backend garantiza que la importación nunca deja un catálogo a medias (transacción ACID).
- **Alternatives considered**: (a) Excel binario (dependencia pesada, parseo frágil); (b) API de operaciones individuales (exigiría muchas llamadas y rompe la atomicidad de la importación); (c) formato XML propietario (innecesario para este alcance).

## D4. Validación de vigencia: rechazo de solapes

- **Decision**: se añade un **trigger PostgreSQL** `trg_catalogo_version_vigencia` (BEFORE INSERT/UPDATE) que rechaza, por `empresa_id`, cualquier `CatalogoVersion` con rango que se solape con otra existente. La lógica se duplica en el servicio para dar respuestas 422 legibles, pero la garantía definitiva es el trigger (constitución: validación en el punto más cercano a la persistencia).
- **Rationale**: cumple FR-006/SC-004 (0 % de vigencias solapadas); el patrón hereda el estilo de triggers del `plan.md` raíz (estructura, selectable, protección, auditoría).
- **Alternatives considered**: solo validación en servicio (susceptible a carreras de escritura concurrentes); constraint excluyente de rangos (no soportado nativamente en PostgreSQL para intervalos superpuestos → se implementa con trigger + `SELECT ... FOR UPDATE` sobre la empresa en la misma transacción).

## D5. Mapeo de cuentas y bloqueo de activación

- **Decision**: `MapeoCuenta` es una relación explícita `(version_origen_id, version_destino_id, cuenta_origen_id, cuenta_destino_id NULL, tipo_movimiento, requiere_reclasificacion)`. La **activación** de una versión (estado `borrador → vigente`) invoca `validar_mapeo_completo`: (a) toda cuenta `suprimida` o `renombrada` con saldo ≠ 0 debe tener mapeo con destino; (b) si el mapeo deja una cuenta sin destino, la activación se bloquea (422 con la lista). La cuenta suprimida puede heredar mapeo por defecto (misma cuenta código) cuando la norma la reubica con igual código; dicho mapeo se autogenera y se audita como `MAPEO_AUTOGENERADO`.
- **Rationale**: cumple FR-002/FR-004 y los edge cases ("EL mapeo deja una cuenta sin destino → se bloquea"; "cuenta suprimida con saldo ≠ 0 → requiere mapeo explícito"). La autogeneración con auditoría evita que migraciones masivas queden atascadas por omisión, pero sin ocultar cuándo se actuó por defecto.
- **Alternatives considered**: imponer siempre mapeo manual (alto coste en PGC masivos); permitir baja con saldo ≠ 0 sin mapeo (viola FR-004).

## D6. Reclasificación de saldos y cuadre de apertura (SPEC-009)

- **Decision**: la reclasificación se modela con `ReclasificacionSaldo` (versión destino, cuenta origen, cuenta destino, importe `NUMERIC(18,4)`, asiento), materializada mediante **asientos `ADJUSTMENT`** del motor de SPEC-002 (Debe/Haber según naturaleza: activo/pasivo). Al confirmar, se generan los asientos de reclasificación balanceados en la misma transacción ACID que los registra (constitución I) y quedan vinculados al asiento de apertura de SPEC-009 (cuadre `Sum(saldos origen) == Sum(saldos destino)`). Se verifica que la suma de saldos reclasificados por código de cuenta cuadra antes de marcar la versión como lista para apertura.
- **Rationale**: cumple FR-005/SC-003 y SC-005 (precisión 4 decimales sin errores de redondeo); respeta la inmutabilidad: los asientos históricos no cambian, solo se crean movimientos nuevos de trasvase.
- **Alternatives considered**: (a) mover el saldo "en memoria" solo a nivel de informe (deja los libros sin trazabilidad contable — se descarta); (b) regenerar la apertura directamente reescribiendo el asiento de apertura (violación de inmutabilidad II).

## D7. Numeración de versión correlativa

- **Decision**: `numero_version` correlativo por `empresa_id`, asignado **dentro de la misma transacción ACID** que persiste la versión sobre una secuencia bloqueada (`SELECT ... FOR UPDATE` de un contador por empresa o una secuencia PostgreSQL particionada por empresa), sin saltos ni duplicados (constitución IV).
- **Rationale**: la versión es un documento normativo de la empresa; la correlatividad es trazable y exigible en auditoría. Alternativa equivalente: `(empresa_id, ejercicio)` único — se descarta porque una empresa puede crear varias versiones dentro del mismo ejercicio (p. ej. PGC + actualizaciones parciales).
- **Alternatives considered**: UUID sin número secuencial (rompe trazabilidad correlativa de la constitución IV); número global de plataforma (rompe la localidad por empresa).

## D8. Multi-tenancy y aislamiento con el plan raíz

- **Decision**: todas las tablas llevan `empresa_id` en PK compuesta e índices; las FKs compuestas `(empresa_id, account_id)` impiden enlazar una cuenta de otra empresa (mismo patrón que `fk_account_plan_parent` del `plan.md` raíz). El `empresa_id` derivar exclusivamente de la sesión autenticada (`deps.py`), nunca del body/path. Se incluyen pruebas de integración que demuestran 404/403 cruzados.
- **Rationale**: constitución III; el patrón reutiliza la convención `tenant_id`/`empresa_id` del plan raíz (alias documentado en data-model.md).
- **Alternatives considered**: aislamiento por esquema por empresa (fuera del alcance fijado por el plan raíz, que usa `tenant_id` en fila).

## D9. Auditoría de operaciones de versionado

- **Decision**: `alta_version`, `importacion`, `activacion`, `resolucion_fallback` y `reclasificacion` escriben en `audit_log` (actores reales o `system` para autogenerados), en la misma transacción ACID, con payload JSONB serializando importes como strings decimales (prohibido `float`).
- **Rationale**: cumple la norma de la constitución (auditoría inmutable WORM, mismo bloque transaccional, actor/UTC/IP/acción/payload).
- **Alternatives considered**: auditoría diferida en un worker (rompe la atomicidad exigida por la constitución).

## D10. Stack e integración

- **Decision**: backend **FastAPI async + SQLAlchemy async + asyncpg**; servicios en `async with async_session.begin()`; frontend Next.js llama al API con la cabecera de empresa activa. La resolución histórica se ofrece como endpoint público (`GET /api/v1/catalogo/vigente`) y como utilidad interna reutilizable por SPEC-002.
- **Rationale**: coherencia con constitución y plan raíz; las reglas de vigencia/mapeo se ejecutan en el backend (Deberes FR-003/004/006).
- **Alternatives considered**: resolver vigencia solo en el frontend (inseguro y duplicado); servicio síncrono acoplado al motor de asientos (rompe la separación de capas del plan raíz).