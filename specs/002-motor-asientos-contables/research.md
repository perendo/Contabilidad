# Research: Motor de Asientos Contables (SPEC-002)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Resoluciones de los unknowns del Technical Context y decisiones de diseño conforme a la constitución y al plan raíz.

## D1. Modelado cabecera + líneas separadas

- **Decision**: `JournalEntry` (cabecera) y `JournalEntryLine` (apuntes) como entidades separadas unidas por FK compuesta `(empresa_id, entry_id)`. La persistencia es **indivisible**: `async with async_session.begin()` inserta cabecera y líneas juntas; si cualquier validación falla, no queda ningún rastro parcial (FR-004).
- **Rationale**: La cabecera transporta numeración/estado/auditoría y las líneas los importes; la actítica indivisible cumple la constitución ("persistir cabecera sin líneas o viceversa PROHIBIDO fuera de transacción ACID").
- **Alternatives considered**: Líneas como JSONB en la cabecera (impide constraints/triggers por línea y consultas de Mayor/Sumas y Saldos en SPEC-004); entidad única desnormalizada (rompe la partida doble por línea).

## D2. Patrón de numeración correlativa por (empresa, ejercicio)

- **Decision**: Contador por `(empresa_id, ejercicio)` sobre una tabla/registro `journal_sequence` bloqueada con **`SELECT ... FOR UPDATE`** dentro de la misma transacción en que se asienta el asiento; `numero = contador+1` persistido como `UNIQUE (empresa_id, ejercicio, numero)`. Los números emitidos en una transacción que revierte **no se reutilizan** (constitución IV).
- **Rationale**: La secuencia bloqueada garantiza correlatividad sin saltos ni duplicados bajo concurrencia (FR-005); el bloqueo se mantiene hasta el commit, serializando los asentados por (empresa, ejercicio).
- **Alternatives considered**: `BIGSERIAL` global (porta saltos y números por ejercicio erróneos); secuencia PostgreSQL dedicada por (empresa, ejercicio) creada dinámicamente (costosa de gestionar a escala); número calculado por `max+1` sin bloqueo (carrera → duplicados).

## D3. Refuerzo del balance a nivel de base de datos

- **Decision**: Además de validar en el servicio (punto de persistencia), un **trigger DB** (`chk_journal_entry_balance`) recalcula `sum(Debe)` y `sum(Haber)` de las líneas de la cabecera en cada mutación y rechaza si no son exactamente iguales. Regla de mínimos: al menos un apunte con `debit > 0` y uno con `credit > 0`.
- **Rationale**: Constitución I exige balance en el punto más cercano a la persistencia; el trigger convierte el invariante en garantía de datos (protege frente a queries/scripts que ignoren el servicio).
- **Alternatives considered**: Solo validación de servicio (débil ante escrituras no vía API); constraint `CHECK` simple en cada línea (no cubre la suma global).

## D4. Estados y transiciones del asiento

- **Decision**: `estado ∈ {DRAFT, POSTED, CANCELLED}` y `tipo ∈ {GENERAL, REVERSAL}`. Transiciones permitidas: `DRAFT → POSTED` (asenta y **asigna número** atómicamente) y `POSTED → CANCELLED` (solo vía REVERSAL enlazado). Un `CANCELLED` no se anula de nuevo (FR-011). El número se asigna **en el asentado**, no en el borrador.
- **Rationale**: Da sentido al ciclo borrador sin que los no asentados consuman número (los borradores no figuran en la correlatividad del diario); FR-011 exige exponer y controlar las transiciones.
- **Alternatives considered**: Creación directa como POSTED con número (pierde el estado borrador que la spec contempla); asignar número al DRAFT (consume números por borradores nunca asentados → saltos).

## D5. Anulación mediante REVERSAL

- **Decision**: `POST /entries/{id}/reverse` genera en **la misma transacción** un nuevo asiento tipo `REVERSAL` con los **importes invertidos** (Debe ⇄ Haber), mismo número de líneas, `tipo=REVERSAL`, `reversal_of_id = id original` y numeración correlativa; el original pasa a `CANCELLED` y **no se modifica en nada más**. El rectificativo queda `POSTED` e inmutable (FR-009).
- **Rationale**: Constitución II (inmutabilidad del original, corrección por rectificativo enlazado); SC-004 exige suma neta cero.
- **Alternatives considered**: Modificar el original (prohibido); borrador de corrección sin vínculo (pierde trazabilidad); reutilizar el número del original (rompe correlatividad).

## D6. Ejercicio derivado de la fecha y rechazo de cerrados

- **Decision**: `ejercicio` se deriva de `fecha` del asiento (nunca se introduce); se valida contra la tabla de ejercicios (`fiscal_year`) de la empresa (provisionada por SPEC-004): si la fecha no pertenece a ningún ejercicio definido → HTTP 400; si el ejercicio está **cerrado** (`is_closed`) → HTTP 400 sin persistir nada (FR-007 de SPEC-004).
- **Rationale**: La spec asume ejercicios provisionados; el bloqueo de periodos cerrados lo impone el cierre de SPEC-004; la guarda se integra aquí para que el cierre sea efectivo.
- **Alternatives considered**: ¿No validar ejercicio? (permite escrituras en periodos cerrados → corrompe el cierre); crear ejercicio automáticamente (excluido por la spec).

## D7. Precisión monetaria canónica de 4 decimales

- **Decision**: Todos los importes en `NUMERIC(18,4)`/`Decimal`; las entradas se **normalizan a 4 decimales** con redondeo decimal canónico (contexto `ROUND_HALF_EVEN` o el fijado por la plataforma) y el balance se valida sobre la **precisión canónica**. Prohibido `float` en todo el flujo (FR-006).
- **Rationale**: Evita falsos descuadres por redondeo y cumple la constitución (prohibido coma flotante); la validación sobre el valor canónico hace determinista el balance.
- **Alternatives considered**: Aceptar más de 4 decimales y comparar con tolerancia (estado indeterminado y no auditable); `float` para comparar sumas (prohibido).

## D8. Validación de cuentas del plan (apuntables y mismA empresa)

- **Decision**: La línea referencia la cuenta por FK compuesta `(empresa_id, account_id)` → `account_plan(tenant_id, id)` y el **trigger** `chk_journal_line_account_selectable` (plan raíz §5.d) exige en el punto de persistencia que la cuenta sea de la **misma empresa**, `is_selectable = true` e `is_active = true` (FR-003). El servicio valida lo mismo antes de insertar para devolver 422/404 amigables.
- **Rationale**: Constitución III (aislamiento en datos) e I (apunte solo sobre cuenta apuntable); el trigger es la garantía última.
- **Alternatives considered**: Validar solo en servicio (riesgo de apuntes a cuentas de cargo vía SQL); solo trigger (errores poco amigables para el usuario).

## D9. Inmutabilidad de `POSTED`/`CANCELLED` en base de datos

- **Decision**: Triggers en `journal_entry` y `journal_entry_line` que **deniegan `UPDATE`/`DELETE`** sobre filas cuyo estado sea `POSTED`/`CANCELLED` (constitución II / FR-008); la API tampoco expone update/delete. El `payload` de las líneas es de solo escritura una vez asentado.
- **Rationale**: La inmutabilidad debe quedar garantizada a nivel de datos, no solo por disciplina de aplicación.
- **Alternatives considered**: Único trigger de API (débil); soft-delete (complejidad sin necesidad).

## D10. Libro diario paginado por fechas

- **Decision**: Endpoint `GET /api/v1/journal/entries?date_from&date_to&page&page_size` que devuelve solo `POSTED`/`CANCELLED` de la empresa activa, ordenados por `(fecha, numero)` asc, con filtro de fechas **obligatorio**, total de registros y paginación sin saltos; índice `(empresa_id, fecha, numero)`.
- **Rationale**: FR-007 (filtro obligatorio y paginación); el motor de paginación por offset es suficiente en el rango del feature (millones de filas por empresa se re-evaluaría con keyset).
- **Alternatives considered**: Paginación keyset (más eficiente a escala; se documenta como evolución); sin filtro de fechas (viola FR-007).

## D11. Auditoría en la misma transacción ACID

- **Decision**: Cada creación (DRAFT), asentado (POSTED) y anulación (REVERSAL/CANCELLED) escribe su fila en `audit_log` **dentro de la misma transacción** con `empresa_id`, actor, acción, entidad, `entity_id`, IP y `payload` JSONB con los importes como **cadenas Decimal** (FR-010). El registro no puede omitirse: un fallo de auditoría aborta la operación.
- **Rationale**: Constitución (auditoría inmutable, misma transacción, actor+UTC+IP+payload, sin float).
- **Alternatives considered**: Auditoría asíncrona/colas (pierde atomicidad); payload numérico flotante (prohibido).

## D12. Stack e integración

- **Decision**: Backend **FastAPI async + SQLAlchemy 2.x async + asyncpg** en los servicios de `journal/`; los servicios de escritura usan `async with async_session.begin()`; frontend Next.js con formulario optimizado al teclado (la validación de balance en UI es informativa, nunca autoritativa).
- **Rationale**: Coherencia con la constitución y el plan raíz; el balance se valida en el backend/DB.
- **Alternatives considered**: Validación de balance en el frontend (prohibida como única); transacciones por endpoint sin bloques `async with` (rompe atomicidad cabecera/línea).