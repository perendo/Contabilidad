# Research: Amortizaciones del Inmovilizado (SPEC-014)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Resoluciones de los unknowns del Technical Context y decisiones de diseño conforme a la constitución y al plan raíz.

## D1. Métodos de amortización (lineal vs regresivo/degresivo)

- **Decision**: Soportar los dos métodos del spec: **lineal** (cuota constante = coste_amortizable / vida_util) y **regresivo/degresivo** (cuota = porcentaje fijo sobre el valor residual del período, de forma que las cuotas decrecen sin superar nunca el coste amortizable). El método se fija por activo en el alta.
- **Rationale**: FR-002 exige precisamente ambos métodos; el degresivo es la alternativa PGC más común al lineal para equipos informáticos y vehículos.
- **Alternatives considered**: Solo lineal (pierde el requerimiento FR-002); cuota regresiva según tabla de porcentajes por tipo de activo (depende de configuración de grupos; se deja como evolución). El tope `amortizado_acumulado <= coste_amortizable` (FR-006) se aplica como regla de negocio y constraint de base de datos.

## D2. Cálculo de la cuota y prorrateo de períodos parciales

- **Decision**: La cuota periódica se calcula con `Decimal` y contexto `ROUND_HALF_EVEN`. El **prorrateo** de la primera y última cuota sigue la configuración de la empresa: **mensual** (cuota anual / 12, prorrateada por mes completo de alta) o **por días** (`cuota_anual * dias_periodo / 365`, suelo ser un año no bisiesto según convenio PGC; día-a-día entre fecha de alta y ejercicio). El plan se almacena por período (año+mes o período definido) con cuota e importe acumulado.
- **Rationale**: La spec (Assumptions) define el prorrateo por config de empresa; la aritmética con `Decimal` exacto cumple FR-007 y constitución (prohibido `float`).
- **Alternatives considered**: Prorrateo fijo mensual siempre (incumple la variabilidad por días); redondeo por defecto bancario en cada cuota (la suma de redondeos puede exceder el coste; se ajusta la última cuota a `coste - Σ cuotas anteriores` para garantizar FR-006).
- **NEEDS CLARIFICATION**: Confirmar el convenio de días del año (360/365) por empresa y si el prorrateo de alta considera el mes completo o día exacto en el modo mensual.

## D3. Generación de asientos periódicos 681/281 y antidupilcación

- **Decision**: `generar_amortizacion(ejercicio, periodo)` recorre los activos en uso con plan vigente y crea un asiento **681 (Debe) contra 281 (Haber)** por activo y período, balanceado y con numeración correlativa delegada a SPEC-002. La **antidupilcación** se garantiza con un registro `AmortizacionGenerada` único por `(empresa_id, activo_id, ejercicio, periodo)` + constraint de unicidad en base de datos. Un período ya generado se **bloquea** (409) o se **reabre con trazabilidad** (anulación `REVERSAL` del asiento previo y regeneración; nunca UPDATE del asiento `POSTED`).
- **Rationale**: FR-003 exige sin duplicados; la constitución II prohíbe modificar posteados → la reapertura es un `REVERSAL` enlazado.
- **Alternatives considered**: Regeneración con UPDATE del asiento anterior (viola constitución II, descartado); duplicado permitido con aviso (viola FR-003).

## D4. Baja y venta de activos

- **Decision**: La baja registra la amortización hasta la fecha de baja (prorrateo, D2), calcula el **valor neto contable** (`coste − amortización acumulada`) y genera el asiento de baja balanceado: **Debe 281** (acumulada) + **Debe 572/570** (precio venta o 0 en retirada) y **Haber 21x** (coste del activo), con el resultado en **671 (pérdidas) / 771 (beneficios)** como diferencia. Si la venta supera el VNC → 771; si es inferior o retirada → 671. El activo pasa a estado `dado_de_baja` y sale del plan.
- **Rationale**: FR-005 exige el asiento de baja balanceado con resultado por venta calculado con precisión exacta; el tratamiento PGC de 671/771 es estándar.
- **Alternatives considered**: Baja sin asiento (deja el activo en libros → descuadre, descartado); resultado calculado con `float` (prohibido).

## D5. Fechas de inicio, cuota y ejercicio cerrado

- **Decision**: La generación de amortización **solo se permite en el ejercicio abierto** de la empresa (SPEC-004); intentar generar para un ejercicio cerrado → 409. En el alta no se generan asientos retroactivos a ejercicios cerrados (el plan se calcula desde la fecha de alta hacia delante; los períodos previos cerrados no se reabren).
- **Rationale**: FR-004; la constitución y SPEC-004 protegen el cierre.
- **Alternatives considered**: Permitir generación retroactiva con reapertura (solo con flujo explícito de reapertura de ejercicio, fuera del alcance de esta feature); se descarta el retroceso automático.
- **NEEDS CLARIFICATION**: ¿Se admite el alta de un activo con fecha anterior al ejercicio en curso (retroactivo informativo) y cómo debe comportarse el plan en ese caso?

## D6. Corrección y revalorización

- **Decision**: Editar un activo ya amortizado recalcula el **plan futuro** a partir del próximo período, usando como base la amortización acumulada ya posteada; los asientos previos `POSTED` no se tocan (constitución II). Si la corrección reduce la vida útil se ajusta la cuota; si la reduce el coste, se validan las cuotas restantes para que el acumulado no supere el nuevo coste.
- **Rationale**: La spec (Edge Cases) exige recalcarca el plan futuro sin retroceder asientos posteados.
- **Alternatives considered**: Reabrir todo el plan y anular los asientos previos (destructivo y costoso; descartado salvo reapertura explícita con trazabilidad).

## D7. Aislamiento multi-tenant

- **Decision**: Toda consulta de activos, planes, generaciones y bajas filtra por `empresa_id` derivado **exclusivamente de la sesión autenticada** (cabecera de sesión; nunca en path ni body). Generación y baja validan que el activo pertenece a la empresa activa; caso contrario → 404. Pruebas de integración demuestran la imposibilidad de acceder a activos de otra empresa.
- **Rationale**: FR-001 y SC-004; constitución III.
- **Alternatives considered**: Identificar la empresa por datos del cuerpo (prohibido por constitución); esquema por empresa (fuera del stack acordado).

## D8. Stack e integración

- **Decision**: Backend **FastAPI async + SQLAlchemy async + asyncpg**; los servicios `services/inmovilizado/` usan `async with async_session.begin()` y delegan la creación de asientos al motor SPEC-002 (que garantiza balance y numeración en la misma transacción); frontend Next.js llama al API con la cabecera de empresa activa.
- **Rationale**: Coherencia con la constitución y el `plan.md` raíz; no duplica el motor de asientos.
- **Alternatives considered**: Generar los asientos con el servicio propio de 014 emtelejando el modelo de SPEC-002 (duplica validación de balance; se reutiliza el motor).

## D9. Numeración de entidades auxiliares

- **Decision**: El activo se identifica por `UUID` y un **número de activo descriptivo** por empresa (no correlativo legal); la numeración correlativa contable la aporta SPEC-002 en cada asiento. El `numero_periodo`/serie del plan es derivada (ejercicio, período), no una secuencia legal.
- **Rationale**: La constitución IV exige correlatividad para asientos y facturas; el inmovilizado no está en ese catálogo → no se inventa una secuencia innecesaria. Se documenta la no aplicabilidad.
- **Alternatives considered**: Numeración correlativa de activos por (empresa, ejercicio) (no requerida por spec; añade complejidad sin beneficio legal).

## D10. Fixtures y estrategia de prueba

- **Decision**: Los planes esperados se validan con **tablas de prueba calculadas manualmente** (lineal y regresivo, con y sin prorrateo, ajuste de última cuota) en fixtures pytest; la generación se prueba en integración sobre PostgreSQL real verificando asientos balanceados y duplicados de (activo, período).
- **Rationale**: Constitución V; un cálculo de amortización sin valores esperados no es verificable.
- **Alternatives considered**: Cálculo esperado ad-hoc en el test (refleja el mismo error del código); se descarta. NEEDS CLARIFICATION: confirmar si la empresa require cuadre del plan contra los módulos oficiales de la Agencia Tributaria/colegio (tabla de coeficientes por grupo).