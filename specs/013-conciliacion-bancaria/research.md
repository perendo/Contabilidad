# Research: Conciliación Bancaria (SPEC-013)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Resoluciones de los unknowns del Technical Context y decisiones de diseño conforme a la constitución y al plan raíz.

## D1. Formato de fichero de extracto (norma 43/19 vs CSV normalizado)

- **Decision**: Aceptar el fichero de extracto en **norma 43/19** de ancho fijo (codificación ISO-8859-1), tal como lo genera la banca española, y **CSV normalizado** (código UTF-8 con cabecera) equivalente. El parser es **configurable por layout** (posición de fecha, concepto, importe con signo, referencia) para absorber variantes de entidad sin cambio de código. Ambas variantes se mapean a `MovimientoBancario` y se acumulan en el mismo `ExtractoBancario`.
- **Rationale**: La spec (FR-001 e Assumptions) exige "formato interoperable (CSV/XLSX según norma 43/19) sin conexión directa a la banca electrónica". El layout de ancho fijo de la norma 43 es el estándar real de la banca española; el CSV cubre entidades/exportadores sin norma 43.
- **Alternatives considered**: Solo CSV (pierde el estándar bancario); parseo rígido de la norma 43 (rompe con variantes de entidad). UE: formato XLSX/qif desestimados por no estar en la spec.
- **NEEDS CLARIFICATION**: Confirmar el/los layout(s) exactos a soportar en la primera implantación (entidad concreta) y si `XLSX` es imprescindible o basta norma 43/CSV.

## D2. Detección de duplicados de extracto

- **Decision**: Doble control: (1) huella **`sha256(CHARSET='ascii', FILE)`** única por `(empresa_id)`, que rechaza la reimportación byte-a-byte del mismo fichero con 409; (2) regla de negocio por **rango de fechas + saldo inicial/final + número de movimientos de la misma cuenta**, que rechaza solapamientos aunque la huella difiera. El estado del extracto es `importado`/`duplicado`.
- **Rationale**: La huella sola no detecta el mismo extracto renombrado o regrabado; la regla de negocio tampoco sola (un fichero distinto puede coincidir en saldos). El doble control garantiza SC-001 (100 % sin duplicados).
- **Alternatives considered**: Solo `sha256` (barato pero evadible); solo regla de negocio (falsos positivos y coste de consulta). La rutina importable queda idempotente: reimportar un extracto ya `importado` → 409 con referencia al original.

## D3. Algoritmo de emparejamiento (propuesta automática)

- **Decision**: La propuesta automática cruza movimientos del extracto con apuntes de la 572 de la empresa activa **no conciliados** mediante: (1) coincidencia exacta de **importe** (comparación `Decimal`) y (2) **orientación** (apunte en el Debe de la 572 ⇄ movimiento débito, y apunte en el Haber ⇄ movimiento crédito). El cruce se ofrece como **candidato**: si además coincide el concepto normalizado, queda `propuesto` con prioridad alta; si coincide el importe pero no el concepto (edge case de la spec), queda `candidato` con aviso y el usuario decide. Las propuestas son no destructivas hasta aceptación.
- **Rationale**: FR-003 exige "proponer cruces automáticos (importe y orientación deudora/acreedora)". Incluir concepto solo como priorización evita descartar cruces válidos con conceptos distintos.
- **Alternatives considered**: Solo importe exacto (da choques en operaciones repetidas del mismo importe); emparejamiento por fecha-valor/importe con tolerancias (añade falsos positivos; se deja como evolución). NEEDS CLARIFICATION: política para deshacer y re-generar propuestas en períodos grandes (paginación y límites).

## D4. Cruce manual, trazabilidad y ciclo de vida del cruce

- **Decision**: Un `CruceConciliacion` une `MovimientoBancario` + `JournalEntryLine` (apunte 572) con estado `propuesto_candidato/confirmado` y origen `auto/manual`. **Antes** de archivar el período, el usuario puede confirmar o deshacer cruces; **después** de archivar, el cruce es inmutable. Todo cruce (crear, confirmar, deshacer) se audita con actor, timestamp UTC e IP. Un apunte `POSTED` nunca se modifica (constitución II); el cruce es una relación externa.
- **Rationale**: FR-003 y SC-002 exigen cruces trazados y decisión del usuario en casos ambiguos. La inmutabilidad del período archivado cumple la constitución y sustenta el cierre.
- **Alternatives considered**: Cruce irrevocable desde la creación (impide corregir conciliaciones en curso); permitir modificar apuntes al conciliar (violación constitución II, descartado).

## D5. Saldos y definición de diferencia

- **Decision**: Para cada cuenta 572 en conciliación se calcula: (a) **saldo según banco** del extracto importado (saldo final del fichero); (b) **saldo según libros** (suma `Haber-Debe` de apuntes de la 572 en el rango); (c) **diferencia = saldo_banco − saldo_libros**. Además, listado de **pendientes**: movimientos sin cruzar y apuntes de la 572 sin extracto (cheques, débitos). Todos los cálculos en `Decimal`/`NUMERIC(18,4)`, cero exacto comparado como `Decimal("0.0000")` (nunca `==` de coma flotante).
- **Rationale**: FR-004 exige mantener los tres valores por cuenta; la comparación decimal exacta es condición de la constitución y de SC-005.
- **Alternatives considered**: Diferencia calculada en la UI (descarta la precisión del backend; prohibido); comparar saldos con tolerancia (viola la partida doble estricta, descartado).

## D6. Cierre y archivo del período conciliado

- **Decision**: El período conciliado se **cierra** solo si `diferencia == Decimal("0.0000")`; entonces se archiva con `numero_periodo` correlativo por `(empresa_id, ejercicio)` asignado atómicamente (secuencia bloqueada, constitución IV). Si hay pendientes, el cierre **se rechaza (409)** y se devuelve la lista de elementos pendientes sin archivar. Un período archivado es inmutable. La conciliación de un ejercicio cerrado se rechaza (SPEC-002/004).
- **Rationale**: FR-005 exige archivar solo con diferencia cero advirtiendo de pendientes; SC-003. La numeración correlativa por período cumple la constitución IV.
- **Alternatives considered**: Archivar con diferencia abierta marcando anomalía (viola FR-005 y rompe la garantía de cuadre); cerrar sin numerar (incumple constitución IV).

## D7. Aislamiento multi-tenant

- **Decision**: Toda consulta de extractos, movimientos, conciliaciones, cruces, períodos y alertas filtra por `empresa_id` derivado **exclusivamente de la sesión autenticada** (cabecera de sesión; nunca en path ni body). Al importar, la cuenta 572 del fichero se valida contra el plan de cuentas de la empresa activa; un extracto de otra empresa (o de una cuenta ajena) → 404/422 por aislamiento. Pruebas de integración demuestran que una empresa B no ve ni muta datos de la A.
- **Rationale**: FR-002 y SC-004; constitución III (multi-tenancy estricto).
- **Alternatives considered**: Identificar la empresa desde el fichero (dato no confiable del cliente, prohibido por constitución); esquema por empresa (fuera del stack acordado).

## D8. Acoplamiento con las remesas SEPA (SPEC-020)

- **Decision**: La conciliación actúa como **confirmador de cobro** de remesas (SPEC-020, D4): al confirmar un cruce cuyo apunte de 572 corresponde a un cobro de `ReciboRemesa`, el servicio de conciliación notifica al servicio de remesas (`confirmar_cobro_por_conciliacion`), que marca el recibo `cobrado` con la fecha de valor del movimiento, sin crear asiento adicional (el apunte ya existe). La notificación se ejecuta en la **misma transacción ACID** del cruce.
- **Rationale**: SPEC-020 D4 define el marcado manual o conciliación como vías de confirmación; mantener el asiento único evita duplicar el apunte del cobro.
- **Alternatives considered**: Que la conciliación cree un asiento de cobro propio (duplicaría el 572 del apunte ya registrado por la remesa; descartado); desacoplar por cola de eventos (fuera del alcance; menor atomicidad).

## D9. Stack e integración

- **Decision**: Backend **FastAPI async + SQLAlchemy async + asyncpg** en los servicios `services/reconciliation/`; el parser es un servicio puro (sin estado) que devuelve DTOs validados por Pydantic v2; frontend Next.js llama al API con la cabecera de empresa activa. Los servicios de escritura usan `async with async_session.begin()` y persisten la auditoría en la misma transacción.
- **Rationale**: Coherencia con la constitución y el `plan.md` raíz; las reglas de negocio (balance, aislamiento, redondeo) se ejecutan en el backend.
- **Alternatives considered**: Parsear en el frontend (expone reglas de negocio y validez del fichero al cliente; descartado).

## D10. Fixtures y estrategia de prueba del fichero externo

- **Decision**: Los contratos de fichero (`contracts/norma-43-19.md`) se prueban con **fixtures** versionados en `backend/tests/fixtures/` (extracto válido, duplicado, de otra empresa, malformado, CSV normalizado). El parser se prueba unitariamente contra el layout acordado y el flujo de importación en integración sobre PostgreSQL real.
- **Rationale**: La constitución V exige pytest obligatorio; un formato externo sin fixtures versionados no es verifinable ni regresivamente seguro.
- **Alternatives considered**: Generar ficheros en tiempo de test (frágil y poco representativo); fixtures binarios de un solo caso (no cubre variantes).