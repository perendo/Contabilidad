# Research: Previsión y Flujo de Caja (SPEC-027)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Resoluciones de los unknowns del Technical Context y decisiones de diseño conforme a la constitución y al plan raíz.

## D1. Fuente y obtención del saldo inicial de tesorería

- **Decision**: el saldo inicial de la previsión se obtiene de la **conciliación bancaria (SPEC-013)** (saldo según extracto de la cuenta 572) cuando está disponible para la cuenta; en su defecto (o para cuentas 570), del **balance del motor de asientos** (SPEC-002) sobre las cuentas de tesorería (grupo 5, 570/572). No hay integración bancaria externa (Assumptions).
- **Rationale**: FR-005 exige cruzar el saldo del EFE con la conciliación; el balance de SPEC-002 es la alternativa sin SPEC-013. Mantener ambas fuentes con preferencia a SPEC-013 es pragmático y trazable.
- **Alternatives considered**: (a) solo SPEC-013 (falla si la empresa no concilia cuentas 570); (b) solo motor SPEC-002 (ignora el dato del banco exigido por FR-005).

## D2. Algoritmo de proyección: día, semana o mes

- **Decision**: la previsión se proyecta por **periodo de agregación elegido por el usuario** (`dia`, `semana`, `mes`). El algoritmo: (1) se obtienen los `MovimientoPrevision` (vencimientos pendientes de SPEC-011/020 + cobros/pagos manuales) con su fecha prevista; (2) se agrupan por el bucket de la granularidad; (3) se calcula el saldo acumulado: `saldo_k = saldo_inicial + Σ(movimientos hasta k)`. El saldo de cada bucket se persiste en la tabla de líneas de la previsión (o se devuelve calculado en el GET). Para semana se agrupa por lunes de la ISO week; para mes por `fecha_inicio` del mes.
- **Rationale**: cumple FR-001/FR-002; la agregación es determinista y testeable (SC-001/SC-002). Persistir las líneas del bucket permite alertas históricas y consultas posteriores sin recálculo.
- **Alternatives considered**: (a) generar solo en memoria (la consulta repetida recarga el cálculo y pierde trazabilidad de las alertas); (b) proyección día a día siempre (CPU innecesaria para empresas que solo quieren mes).

## D3. Tratamiento de vencimientos y pagos no datados

- **Decision**: un vencimiento **pendiente sin fecha de vencimiento resolvible** se excluye de la proyección salvo que el usuario le asigne una **fecha estimada** en `MovimientoPrevision` (columna `fecha_prevista`). Un vencimiento **vencido y ya cobrado/pagado** se excluye (FR-006). Un **pago recurrente** (alquiler, nómina) sin vencimiento se inserta manualmente como `MovimientoPrevision` con tipo `pago_recurrente` y frecuencia (`mensual`, `semanal`, `anual`) o como importe único.
- **Rationale**: cumple los edge cases de la spec ("Solo se incluyen si tienen fecha prevista estimada; sin fecha quedan fuera"; "vencidos y cobrados se excluyen"); la tabla de movimientos manuales da trazabilidad sin depender de la generación previa de vencimientos en SPEC-007.
- **Alternatives considered**: (a) suponer cobro/pago inmediato para los no datados (distorsiona la previsión); (b) incluir vencidos (rompe FR-006).

## D4. Clasificación EFE por tipo de actividad

- **Decision**: el EFE se construye clasificando cada **cuenta contable en una de las tres actividades**: **operativa** (grupos 6/7 y tesorería operativa 570/572 en movimientos operativos), **inversión** (grupo 2, inversiones del inmovilizado y cuentas del 8/23), **financiación** (grupo 1/9 y cuentas de deudas 16/17). Una tabla de configuración por empresa (`clasificacion_actividad_cuenta`, con override manual) permite al usuario reclasificar cuentas antes de generar el informe (edge case "no clasificadas → se clasifican por defecto por grupo y se permite reasignar"). Importes: para cada cuenta se usa su saldo activo con signo según el movimiento en 572/570 (cobros = +, pagos = −), todo en `Decimal`.
- **Rationale**: cumple US2 (tres bloques con categorías) y FR-004; la inferencia por grupo del plan (SPEC-001) es el estándar del PGC español y un override trazable por empresa la respeta.
- **Alternatives considered**: (a) clasificación 100% manual (excesiva por apiñamiento de cuentas); (b) heurística sin override (no permite ajustes de la emprea).

## D5. Cuadre del EFE y cruce con la conciliación bancaria

- **Decision**: el EFE se valida con `saldo_inicial + Σ movimientos operativos/inversión/financiación = saldo_final` (constitución I, aritmética Decimal). El `saldo_final` se contrasta con el saldo de **conciliación bancaria (SPEC-013)** de las cuentas 572/570; si hay diferencia por movimientos no conciliados, el EFE se marca como `sin_conciliar` (query de advertencia) pero se permite formular con aviso (Assumptions de SPEC-027). No se exige coincidencia exacta (puede haber movimientos no conciliados, SPEC-013).
- **Rationale**: FR-004/FR-005 exigen el cuadre interno y el cruce con la conciliación; no exigir el 100% de coincidencia respeta la Assumptions de la spec y evita bloqueos indebidos.
- **Alternatives considered**: bloquear si el saldo no cruza (excesivo según Assumptions); ignorar completamente SPEC-013 (pierde la validación cruzada de FR-005).

## D6. Mecanismo de alerta de liquidez

- **Decision**: al generar una previsión, el servicio `detectar_alertas` recorre los buckets de la proyección y crea `AlertaLiquidez` para todo bucket con `saldo_proyectado < 0` (FR-003). El saldo exactamente cero se marca como `límite de solvencia` sin alerta (edge case de la spec). La alerta incluye `fecha`, `saldo_proyectado`, `importe_deficit`, `estado` y `accion_sugerida` (`reprogramar_pago` o `incluir_ingreso`). La acción `reprogramar_pago` actualiza la `fecha_prevista` de un `MovimientoPrevision` (traslada el pago); `incluir_ingreso` crea un `MovimientoPrevision` de cobro. Cada acción queda auditada.
- **Rationale**: cumple US3/FR-003 y el edge case de saldo cero; las acciones operativas sobre movimientos son trazables y reversibles con `estado` de alerta (`abierta`, `atendida`, `ignorada`).
- **Alternatives considered**: (a) alerta solo informativa sin acciones (no permite "planificar pagos o buscar financiación" del scenario); (b) re-despacho por email (fuera de alcance, sin infraestructura de notificaciones en esta feature).

## D7. Numeración de previsión correlativa

- **Decision**: `numero_prevision` correlativo por empresa, asignado atómicamente dentro de la misma transacción ACID sobre secuencia bloqueada (constitución IV), sin saltos; usado como identificador visible de la previsión.
- **Rationale**: la previsión es un documento de gestión del usuario; la correlatividad por empresa refuerza la auditoría y cumple la constitución IV. El EFE es único por ejercicio, no requiere numeración propia.
- **Alternatives considered**: UUID visible únicamente (rompe trazabilidad correlativa exigida por la constitución IV).

## D8. Multi-tenancy y aislamiento

- **Decision**: todas las tablas incluyen `empresa_id` en PK compuesta e índices; el `empresa_id` se deriva exclusivamente de la sesión; las FKs compuestas `(empresa_id, cuenta_id)` y `(empresa_id, vencimiento_id)` impiden enlazar datos de otra empresa. Pruebas de integración demuestran 404/403 cruzados.
- **Rationale**: constitución III; mismo patrón que el `plan.md` raíz y las features previas.
- **Alternatives considered**: aislamiento por esquema (fuera del alcance del plan raíz).

## D9. Auditoría y stack

- **Decision**: generación de previsión, creación/modificación de `MovimientoPrevision`, generación de alertas, reprogamación de pagos y formulación de EFE se auditan en `audit_log` en la misma transacción ACID con actor, UTC, IP y payload con importes como `Decimal` strings (prohibido `float`). Backend FastAPI async + SQLAlchemy async + asyncpg en `async with async_session.begin()`. Frontend Next.js consume `/api/v1/tesoreria/...` con cabecera de empresa activa.
- **Rationale**: coherencia con la constitución (auditoría WORM, ACID) y el stack del plan raíz.
- **Alternatives considered**: auditoría diferida (rompe atomicidad); servicios síncronos (violan stack async).