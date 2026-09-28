# Research: Multi-Divisa (SPEC-016)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Resoluciones de los unknowns del Technical Context y decisiones de diseño conforme a la constitución y al plan raíz.

## D1. Moneda funcional por empresa y divisas de trabajo

- **Decision**: Una empresa tiene **una moneda funcional** (ISO 4217, por defecto EUR para las empresas españolas) y un conjunto de **divisas de trabajo** autorizadas. La moneda funcional se fija en la creación de la empresa (SPEC-003) y es inmutable salvo migración formal (documentada y auditada). Las transacciones en otra divisa se convierten con el tipo de cambio de la fecha (FR-001).
- **Rationale**: FR-001 pide una moneda funcional por empresa; la misma spec (Assumptions) no contempla multi-funcional por ejercicio. Trabajar solo con divisas autorizadas evita entradas con divisas no gestionadas.
- **Alternatives considered**: Varias monedas funcionales por ejercicio (exige una contabilidad multi-registro mucho mayor; fuera de alcance); permitir cualquier ISO 4217 en cada asiento (complica catálogo y validaciones).
- **NEEDS CLARIFICATION**: ¿Debe permitirse el cambio formal de moneda funcional de una empresa existente y con qué plano de migración de saldos?

## D2. Tipos de cambio: fecha, histórico y sellado

- **Decision**: `TipoCambio` es **único por `(empresa_id, divisa, fecha)`** con el ratio `divisa → funcional` (1 unidad de divisa = ratio de funcional). El histórico es **inmutable**: un tipo usado por al menos un asiento `POSTED` se **sella** (`sellado = true`) y queda prohibida su modificación o borrado (constitución II). Un tipo sin asientos asociados puede corregirse con trazabilidad (audit). Ratios en `NUMERIC(18,8)`.
- **Rationale**: FR-002 exige "histórico inmutable una vez usados en asientos posteados"; sellar el tipo con un flag persistido (más el contador de usos) hace la restricción verificable y auditable.
- **Alternatives considered**: Recalcular siempre desde un feed externo (los tipos históricos deben vencerse y congelarse para reproducir asientos, FR-003); sobreescribir el tipo (viola la inmutabilidad; descartado).
- **NEEDS CLARIFICATION**: ¿Los tipos los introduce el usuario, provienen de un importador (BCE/feed) o ambos? (El feed no está en la spec; por defecto entrada manual con posible import futuro.)

## D3. Conversión y redondeo (que nunca desequilibra)

- **Decision**: Conversión con aritmética `Decimal` y contexto de redondeo **`ROUND_HALF_EVEN`** configurable por empresa (Assumptions: half-even por defecto). El equivalente funcional de cada línea se redondea a **4 decimales**. Si la suma de líneas redondeadas deja un **remanente** (el total funcional ≠ Σ líneas funcionales exactas), se imputa a una **línea de ajuste de redondeo** (cuenta de diferencias `668/769` o similar configurada) para que el asiento **cuadre siempre exactamente en funcional** (constitución I). No se acepta la creación del asiento si el desequilibrio no es imputable.
- **Rationale**: FR-004 exige una regla acordada que jamás desequilibre; el remanente de 4 decimales es inevitable con tipos de un solo sentido y múltiples líneas; imputarlo a una línea contable visible es el método PGC-consistente.
- **Alternatives considered**: Guardar más decimales en funcional (18,8) y redondear solo a presentación (los totales de libros exigen 4 decimales exactos; no se sostiene contra el balance); descartar el asiento si hay remanente (bloquea operaciones legítimas).
- **NEEDS CLARIFICATION**: cuenta de redondeo por defecto (668 "Diferencias negativas de cambio"/769 "Diferencias positivas") y su configuración por empresa.

## D4. Cuadre en doble moneda (divisa y funcional)

- **Decision**: Un asiento en divisa se valida con **Debe==Haber en divisa** (suma de importes en divisa por signo) **y** con **Debe==Haber en funcional** (líneas convertidas más ajustes de redondeo). Ambas comprobaciones en el backend, junto a la persistencia. El `empresa` funcional es la de la empresa activa; la divisa del asiento es una de las de trabajo.
- **Rationale**: FR-003; la constitución exige balance estricto y este módulo lo exige doble.
- **Alternatives considered**: Validar solo en funcional (deja asientos descuadrados en divisa → saldos incorrectos); validar solo en UI (prohibido por constitución).

## D5. Registro en divisa vs columna de funcional (ampliación de SPEC-002)

- **Decision**: El registro en divisa se modela como **extensión** del motor de SPEC-002 sin tocar los asientos en moneda funcional: `AsientoDivisa` (asiento_id, divisa_id, fecha, tipo_cambio_id sellado, importe_total en divisa) y `LineaDivisa` (linea_id, importe_divisa) para cada línea del `JournalEntryLine`. Un asiento puede verse en funcional (suma de líneas convertidas) y en divisa (columnas de divisa). No se altera la tabla base de líneas.
- **Rationale**: FR-003 exige almacenar importe en divisa, tipo e importe funcional; una tabla adjunta evita migrar millones de asientos existentes y conserva la validación única de balance en un solo lugar (extendida).
- **Alternatives considered**: Añadir columnas `importe_divisa`/`divisa_id` directamente a `JournalEntryLine` (migración masiva y mezcla de semánticas; descartada); asiento espejo duplicado (rompe la correlatividad; descartado).

## D6. Valoración a cierre y asiento de diferencias de cambio

- **Decision**: Al **valorar saldos en divisa** a una fecha de cierre (ejercicio/período), el servicio itera los saldos vivos por cuenta en divisa, recoge el tipo de cierre de la fecha, calcula `saldo_divisa × tipo_cierre − saldo_funcional_pendiente` y genera un **asiento balanceado de diferencias de cambio** (cuenta de diferencias `668` pérdida / `769` ganancia) vinculado al cierre (SPEC-004). El asiento es generado y **revisable** (Assumptions: valorización automática revisable, no abre el ejercicio). No se asienta en ejercicio cerrado (409).
- **Rationale**: FR-005; la Assumption pide generar asientos automáticos revisables sin reabrir el cierre; el vínculo al cierre garantiza trazabilidad.
- **Alternatives considered**: Actualizar el saldo funcional directamente (rompería el diario inmutable y el cuadre doble de SPEC-006); asiento no vinculado al cierre (pierde trazabilidad de cierre; descartado).

## D7. Inmutabilidad del tipo de cambio usado (sellado)

- **Decision**: El **sellado** ocurre en la misma transacción ACID en que el asiento en divisa se posteada: se incrementa el contador de usos del `TipoCambio` y se marca `sellado=true`. Cualquier intento de `PATCH`/`DELETE` sobre un tipo sellado → **409**. El histórico de tipos por (divisa, fecha) es consultable aunque el tipo esté sellado.
- **Rationale**: FR-006 y FR-002; constitución II.
- **Alternatives considered**: Bloquear la edición por fecha de cierre del feed (permite reescribir tipos ya usados antes de la marca; insuficiente).

## D8. Aislamiento multi-tenant de divisas y conversiones

- **Decision**: Toda tabla (monedas funcionales y de trabajo, tipos, asientos en divisa, valoraciones, líneas en divisa) filtra por `empresa_id` derivado de sesión (cabecera; nunca en path ni body). Operar sobre tipos/asientos de otra empresa → 404. Pruebas de integración demuestran que A no ve ni usa los tipos ni los saldos de B.
- **Rationale**: FR-007 y SC-005; constitución III.
- **Alternatives considered**: Catálogo de divisas global sin empresa (razonable para ISO 4217 puro, pero los tipos y las conversiones son por empresa y los saldos requieren aislamiento; se matiene la empresa en todo).

## D9. Bloqueos por falta de tipo y ejercicio cerrado

- **Decision**: Registrar un asiento en divisa **sin tipo de cambio** para la fecha → **422** salvo que el cliente aporte un tipo explícito `(ratio, fecha_valor)` que se persiste como tipo de esa fecha antes de la posteada (misma transacción). Operar en un ejercicio cerrado → **409** (SPEC-002/004). Asientos de diferencia de cambio en ejercicio cerrado → 409.
- **Rationale**: Edge Cases de la spec (sin tipo se bloquea o se exige tipo explícito; ejercicio cerrado se bloquea).
- **Alternatives considered**: Tipo por defecto del día anterior (distorsiona la valoración a la fecha; descartado); permitir postear en cerrado (viola SPEC-004).

## D10. Stack y estrategia de prueba

- **Decision**: Backend **FastAPI async + SQLAlchemy async + asyncpg** en `services/forex/`; conversión como servicio puro sin estado; registros de escritura con `async with async_session.begin()` y auditoría en la misma transacción; frontend Next.js con cabecera de empresa activa. Fixtures de tipos (EUR/USD/GBP) y asientos en divisa con cuadre esperado en ambas columnas calculado a mano.
- **Rationale**: Coherencia con constitution y plan raíz; pruebalidad exacta del doble cuadre y del redondeo.
- **Alternatives considered**: Conversión en frontend (pierde precisión y control; prohibido); fixtures generados por el mismo código (no detectan errores de cálculo; descartado).