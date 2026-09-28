# Research: Presupuestos y Desviaciones (SPEC-026)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Resoluciones de los unknowns del Technical Context y decisiones de diseño conforme a la constitución y al plan raíz.

## D1. Codificación del presupuesto: anual único vs desglose por períodos

- **Decision**: el presupuesto se almacena por **combinación cuenta-centro-ejercicio** como importe anual único (`NUMERIC(18,4)`), sin desglose mensual en el modelo de persistencia. Si el usuario necesita seguimiento mensual (estacionalidad), se derivan desglosamientos parciales en los informes a partir del real acumulado mes a mes, pero el presupuesto registrado es el importe anual.
- **Rationale**: FR-001 dice "importes por cada combinación cuenta-centro y ejercicio"; simplifica el alta masiva (una fila por combinación, no 12×), reduce filas sin perder la posibilidad de informes mensuales comparativos (el real sí se desglosa por mes en el informe).
- **Alternatives considered**: (a) desglose mensual (12 filas por combinación → alta complejidad de carga y query); (b) periodicidad configurable por cuenta (potente, pero excesivo para el alcance inicial de la spec).

## D2. Convención de signos: gastos/ingresos y la desviación

- **Decision**: para cuentas de gasto (grupo 6): `real = SUM(Debe)` en el periodo; para cuentas de ingreso (grupo 7): `real = SUM(Haber)` en el periodo. La desviación absoluta se calcula como `real − presupuesto` (valores positivos significan "se superó el presupuesto"). La desviación relativa es `(real − presupuesto) / |presupuesto|` si presupuesto ≠ 0, `null` si es cero. Los valores se almacenan con signo en `NUMERIC(18,4)` y se exponen con la convención `positive = sobre_gasto`.
- **Rationale**: esta convención es estándar en contabilidad de gestión española; la regla se implementa en una función utilitaria `calcular_signo_real(cuenta, importe_debe, importe_haber)` que aplica la regla por grupo del plan de cuentas (SPEC-001).
- **Alternatives considered**: almacenar directamente `Debe - Haber` (invierte el signo para ingresos → causa confusión); presupuesto de ingresos con signo negativo (propenso a errores de carga).

## D3. Cálculo del real: granularidad y fuente

- **Decision**: el real de un periodo se calcula a partir de los `journal_entry_line` del motor (SPEC-002) filtrados por `(empresa_id, fecha_asiento BETWEEN fecha_inicio_periodo AND fecha_fin, cuenta)`, con agregación `SUM(Debe)` o `SUM(Haber)` según la convención de signos (D2). El periodo es `PeriodoSeguimiento` (rango de fechas del periodo de seguimiento o del ejercicio completo). La agregación se realiza con `NUMERIC` en PostgreSQL (sin `float`); la aplicación lo consume como `Decimal`.
- **Rationale**: cumple FR-002/FR-003; la fuente del real es el motor de asientos (única fuente de verdad contable), lo que garantiza que la desviación refleja el diario exacto.
- **Alternatives considered**: (a) calcular el real con `sum` en Python sobre datos traídos (inscalable bajo miles de líneas); (b) almacenar un snapshot mensual del real en un job batch (exige orchestration extra, se difiere).

## D4. Cuentas sin presupuesto

- **Decision**: cuando una cuenta tiene `real ≠ 0` y no tiene línea de presupuesto para la combinación cuenta-centro-ejercicio, el informe la lista con desviación igual al `real` y `presupuesto = 0`, desviación relativa `null` (dividir entre 0 no tiene sentido financiero). En la tabla de seguimiento aparece como `sin_presupuesto = true` para que el usuario identifique gastos/imprevistos no presupuestados.
- **Rationale**: FR-001/FR-006 exigen que aparezcan; la convención de `null` en relativa es estándar y evita infinitos; `sin_presupuesto = true` se audita en el snapshot del cierre.
- **Alternatives considered**: (a) excluir cuentas sin presupuesto del informe (pierde información útil); (b) tratar como desviación negativa / cero (inexacto).

## D5. Periodo de seguimiento y cierre

- **Decision**: `PeriodoSeguimiento` define un rango de fechas por `(empresa_id, ejercicio)`, con `estado` (abierto/cerrado) y `numero_periodo` correlativo por (empresa, ejercicio). Solo puede haber un periodo abierto a la vez para un ejercicio (constraint). El cierre: (1) bloquea la modificación de presupuestos de ese periodo (FR-004); (2) genera un snapshot `Desviacion` con la desviación final de cada combinación cuenta-centro acumulada, registrado como trazable (US3 scenario 2: "la desviación final queda registrada como trazable").
- **Rationale**: el cierre se materializa como snapshot inmutable (una tabla nueva `Desviacion` con `estado = cerrada`), respetando la filosofía de inmutabilidad por snapshot que aplica la constitución a datos reportados; el snapshot evita recalcular en informes futuros y garantiza trazabilidad histórica.
- **Alternatives considered**: (a) cerrar sin snapshot (obligaría recalcular siempre y pierde la "desviación final" trazable); (b) cierre parcial por mes (premature optimisation).

## D6. Generación de informes: consolidación y periodización

- **Decision**: el informe de desviación (US3) se genera como vista calculada o vista materializada en el backend que recorre las combinaciones `(cuenta, centro, ejercicio)` presentes en el diario o en el presupuesto, calculando la desviación y la acumulación; al cerrar se "solidifica" en la tabla `Desviacion` (snapshot). Los informes se exponen paginados por `(centro, cuenta, ejercicio)`, con la opción de filtrar por rango de fechas parcial (mes) o acumulado anual.
- **Rationale**: FR-003 exige informes por centro y cuenta con acumulación del periodo; el snapshot en cierre trae la desviación "cierre" reutilizable sin recálculo.
- **Alternatives considered**: (a) calcular en tiempo real siempre (costoso a escala); (b) generar el informe como fichero exportable sin snapshot (pierde trazabilidad del cierre).

## D7. Centro de coste: opcional y multi-tenant

- **Decision**: `centro_coste_id` en la línea de presupuesto es `UUID NULL FK → CentroCoste` (SPEC-017) con FK compuesta `(empresa_id, centro_coste_id)` para impide aislamiento cruzado de centros entre empresas. Si SPEC-017 no está activo para la empresa, el campo queda `NULL` y la desviación se calcula solo por cuenta (FR-006). La consulta de "centros disponibles" se hace con `empresa_id` de sesión.
- **Rationale**: FR-001/FR-006; la opcionalidad por empresa permite funcionar sin SPEC-017 activo sin necesidad de vaciar el dato.
- **Alternatives considered**: (a) obligatorio siempre (bloquea a empresas que no usen centros); (b) desnormalizar nombre del centro en el presupuesto (riesgo de desincronización con SPEC-017).

## D8. Numeración de periodo correlativa

- **Decision**: `numero_periodo` correlativo por `(empresa_id, ejercicio)`, asignado atómicamente dentro de la misma transacción ACID sobre secuencia bloqueada (constitución IV), sin saltos.
- **Rationale**: el periodo es un documento de seguimiento trazable; la numeración garantiza secuencialidad para auditoría; el trigger de unicidad `(empresa_id, ejercicio)` en `PeriodoSeguimiento` evita duplicados.
- **Alternatives considered**: UUID sin secuencia (rompe trazabilidad correlativa de la constitución IV).

## D9. Multi-tenancy y aislamiento

- **Decision**: todas las tablas incluyen `empresa_id` en PK compuesta e índices; el `empresa_id` se deriva de la sesión autenticada; `CentroCoste` se referencia con FK compuesta `(empresa_id, centro_coste_id)`. Pruebas de integración demuestran 404/403 cruzados.
- **Rationale**: constitución III; patrón consistente con el `plan.md` raíz (SPEC-001/003).
- **Alternatives considered**: aislamiento por esquema (fuera del alcance del plan raíz).

## D10. Auditoría y stack

- **Decision**: el alta/modificación/cierre de presupuesto y periodo se audita en `audit_log` en la misma transacción ACID, con actor, UTC, IP y payload serializado con `Decimal` strings (prohibido `float`). Backend FastAPI async + SQLAlchemy async en `async with async_session.begin()`. Los servicios de `budget/` son puros de lógica y query (sin estado propio); el frontend consume `/api/v1/presupuestos/...`.
- **Rationale**: constitución (auditoría WORM, ACID) y coherencia con el stack del `plan.md` raíz.
- **Alternatives considered**: auditoría diferida (rompe atomicidad); servicio síncrono (viola stack async).