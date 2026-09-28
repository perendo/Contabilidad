# Research: Apertura del Ejercicio (SPEC-009)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Resoluciones de los unknowns del Technical Context y decisiones de diseño conforme a la constitución y al plan raíz.

## D1. Mecánica de generación del asiento de apertura

- **Decision**: El asiento de apertura se genera como un `JournalEntry` de tipo `OPENING` con líneas (`JournalEntryLine`) por cada cuenta patrimonial que tuviese saldo al cierre del ejercicio anterior. Cada línea refleja el saldo del Debe o Haber de la cuenta patrimonial (grupo 1-3 del PGC). Las cuentas de resultado (grupo 6-7) no se abren; sus saldos ya fueron transferidos a reservas/resultados en el cierre (SPEC-004).
- **Rationale**: La apertura es la continuación del ciclo: cierre regulariza resultados → apertura traslada patrimonio. Solo las cuentas patrimoniales (balance) perpetúan saldos.
- **Alternatives considered**: Abrir también cuentas de resultado (incrementa ruido y no es estándar); saldos calculados en tiempo real sin persistir (pierde trazabilidad).

## D2. Fuente de saldos patrimoniales

- **Decision**: Los saldos se obtienen de la consulta de saldos del plan de cuentas (SPEC-001) filtrando por `ejercicio_id` del cierre, cuentas de grupo 1-3 (activo, pasivo, patrimonio neto) y `empresa_id` de la sesión. Los saldos se calculan como `suma_debe - suma_haber` por cuenta.
- **Rationale**: Reutiliza la funcionalidad existente de saldos del plan de cuentas; la fuente es la misma que el Balance de Situación (SPEC-010).
- **Alternatives considered**: Almacenar snapshot de saldos de cierre en tabla aparte (duplica datos); calcular desde los asientos del ejercicio en cada apertura (lento para ejercicios con muchos asientos).

## D3. Tipos de ejercicio y máquina de estados

- **Decision**: Un ejercicio contable tiene estados: `abierto` → `cerrado` → `con_apertura` → `abierto` (nuevo). El estado `abierto` indica que se puede asentar. `cerrado` significa que el cierre se completó y no admite asientos. `con_apertura` es transitorio tras generar la apertura del siguiente. La apertura es la operación que abre el nuevo ejercicio.
- **Rationale**: Clarifica el ciclo contable y permite validar precondiciones de apertura.
- **Alternatives considered**: Solo dos estados (abierto/cerrado) sin distinguir la apertura (pierde trazabilidad del momento de apertura).

## D4. Precondiciones de apertura

- **Decision**: Antes de generar la apertura se validan: (a) el ejercicio anterior existe y está en estado `cerrado`, (b) el ejercicio siguiente ya está definido (rango de fechas creado), (c) no existe un asiento de tipo `OPENING` para el ejercicio siguiente, (d) el rango de fechas del nuevo ejercicio no se solapa con el anterior.
- **Rationale**: Cumple US3 del spec y previene estados inconsistentes.
- **Alternatives considered**: Permitir apertura sin cierre previo (rompe la continuidad contable); no validar solapamiento (produce ejercicios superpuestos).

## D5. Numeración y transacción atómica

- **Decision**: El número del asiento de apertura se asigna dentro de la misma transacción ACID que persiste el asiento y sus líneas, usando `SELECT ... FOR UPDATE` sobre la secuencia de numeración por (empresa_id, ejercicio). El asiento se persiste como `POSTED` inmediatamente (no hay estado borrador para la apertura).
- **Rationale**: Cumple constitución IV (correlatividad sin saltos) y I (partida doble atómica).
- **Alternatives considered**: Asiento en estado borrador para revisión previa (añade complejidad y retrasa la apertura).

## D6. Anulación y regeneración

- **Decision**: Si la apertura es errónea, el usuario solicita la anulación. El sistema genera un asiento `REVERSAL` del asiento de apertura original (Debe/Haber invertidos) enlazado al original con tipo `OPENING_REVERSAL`. Después, se permite regenerar la apertura creando un nuevo asiento `OPENING` con los saldos recalculados. El asiento original de apertura permanece inmutable (constitución II).
- **Rationale**: La inmutabilidad exige corrección por reversión, no por mutación. La regeneración es simplemente una nueva apertura tras la anulación.
- **Alternatives considered**: Borrar y regenerar (viola inmutabilidad); solo anular sin regenerar (deja sin apertura al ejercicio).

## D7. Validación de balance estricto

- **Decision**: Antes de persistir, el servicio verifica que `suma(líneas_Debe) == suma(líneas_Haber)` con aritmética `Decimal`. Si no cuadra, la transacción se revierte y se devuelve error 422 `asiento_desbalanceado`.
- **Rationale**: Constitución I — la validación está en el backend, no en la UI.
- **Alternatives considered**: Validación solo en UI (prohibido por constitución); validación post-commit (demasiado tarde).

## D8. Bloqueo de ejercicio cerrado

- **Decision**: Cualquier intento de apertura o anulación sobre un ejercicio cerrado que no sea el previo al cierre se rechaza con 409 `ejercicio_cerrado`. La anulación solo se permite si el ejercicio de la apertura sigue abierto.
- **Rationale**: Constitución — no se pueden ejecutar operaciones de escritura sobre ejercicios cerrados.
- **Alternatives considered**: Permitir anulación en ejercicios cerrados con permiso especial (complica la lógica y la constitución no lo prevé).

## D9. Multi-tenancy en la apertura

- **Decision**: El `empresa_id` se obtiene exclusivamente de la sesión autenticada y se propaga a todas las queries de saldos, ejercicio y asientos. Se realizan pruebas de integración que demuestran que la empresa A no puede ver ni manipular la apertura de la empresa B.
- **Rationale**: Constitución III — aislamiento total.
- **Alternatives considered**: empresa_id en el body (menos seguro, permitiría cross-tenant).
