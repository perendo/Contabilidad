# Research: Impuesto sobre Sociedades (Modelo 200) (SPEC-023)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Resoluciones de los unknowns del Technical Context y decisiones de diseño conforme a la constitución y al plan raíz.

## D1. Obtención del resultado contable del ejercicio

- **Decision**: El resultado contable se obtiene del **cierre de ejercicio** (SPEC-004): suma de ingresos menos gastos del periodo, reflejado en las cuentas de resultado (6/7). Se consulta como un `Decimal` calculado a partir de los asientos confirmados del ejercicio; no se almacena como campo derivado.
- **Rationale**: La fuente de verdad son los asientos del diario; calcular en tiempo de consulta garantiza consistencia.
- **Alternatives considered**: Almacenar el resultado en una tabla resumen (riesgo de desincronización si se modifican asientos del periodo).

## D2. Cuentas PGC para el IS

- **Decision**: Asiento del IS: **Debe 630** (impuesto sobre beneficios) | **Haber 473** (Hacienda pública, deudora por IS — pagos a cuenta) + **4752** (Hacienda Pública, acreedora por retenciones y ingresos a cuenta) o **4757** (Hacienda Pública, acreedora por otros conceptos) según el saldo. La **cuota diferencial** (a pagar = 473 < cuota íntegra; a devolver = 473 > cuota íntegra) se refleja en 4709 (Hacienda pública, acreedora por devoluciones) o se mantiene en 473.
- **Rationale**: Cuentas estándar del PGC español para el IS (Real Decreto 1514/2007, apartado 6.ª del Plan General de Contabilidad).
- **Alternatives considered**: Usar solo 473 sin 4752/4757 (simplifica pero pierde trazabilidad de pagos a cuenta vs cuota diferencial).

## D3. Tipo impositivo y configuración por empresa

- **Decision**: El tipo impositivo es un **parámetro configurable por empresa** con valor por defecto del **25%** (tipo general). Se almacena en `ConfiguracionFiscal` por `empresa_id` con `tipo_is`, `fecha_vigencia_desde`, `fecha_vigencia_hasta`. El sistema usa el tipo vigente al último día del ejercicio.
- **Rationale**: El tipo puede cambiar (reformas fiscales); las empresas pueden tener tipos especiales (reducidos, en régimen de consolidación).
- **Alternatives considered**: Tipo fijo hardcodeado (no realista); tipo calculado automáticamente (excesiva complejidad).

## D4. Ajustes extracontables

- **Decision**: Los ajustes se introducen **manualmente** con descripción, referencia normativa e importe (positivo o negativo). Se almacenan en `AjusteExtracontable` con empresa, ejercicio y tipo (positivo/negativo). La base imponible = resultado contable + suma(ajustes positivos) - suma(ajustes negativos). Los ajustes son trazables pero no generan asiento por sí mismos.
- **Rationale**: Los ajustes son declarativos y de uso del gestor fiscal; no tienen impacto contable directo.
- **Alternatives considered**: Ajustes vinculados a asientos (doble contabilización innecesaria); ajustes derivados automáticamente (excesiva complejidad fiscal).

## D5. Deducciones y bonificaciones

- **Decision**: Las deducciones/bonificaciones se registran de forma similar a los ajustes: descripción, referencia normativa, importe y tipo (deducción/bonificación). Se descuentan de la cuota íntegra para obtener la cuota líquida antes de pagos a cuenta. Se almacenan en la misma tabla `AjusteExtracontable` con un campo `tipo` diferenciador.
- **Rationale**: Simplifica la tabla; la distinción entre ajuste y deducción se hace por el campo `tipo`.
- **Alternatives considered**: Tabla separada para deducciones (más normalizada pero más tablas para un volumen bajo de registros).

## D6. Pagos a cuenta (473)

- **Decision**: Los pagos a cuenta se obtienen de los **asientos ya contabilizados en la cuenta 473** del ejercicio (retenciones, pagos fraccionados). Se calcula como la suma de Debe de la cuenta 473 en el ejercicio. El sistema consulta directamente el submayor de la cuenta 473; no se almacena como dato separado del IS.
- **Rationale**: La fuente de verdad es el diario contable; duplicar la información crea riesgo de desincronización.
- **Alternatives considered**: Tabla separada de pagos a cuenta (requiere sincronización manual).

## D7. Cálculo provisional en cierres intermedios

- **Decision**: El cálculo provisional se permite en cualquier momento del ejercicio con una marca `provisional=true`. Se sobrescribe al recalcular; el cálculo definitivo se marca `provisional=false` al cerrar el ejercicio. Solo un cálculo definitivo por ejercicio; los provisionales pueden sobrescribirse libremente.
- **Rationale**: Cumple FR-007; los cierres intermedios necesitan estimaciones provisionales del IS.
- **Alternatives considered**: No permitir provisionales (no cubre el caso de cierres intermedios); múltiples provisionales con histórico (excesiva complejidad para MVP).

## D8. Generación del modelo 200

- **Decision**: El modelo 200 se genera como un **informe/descargable** (PDF o CSV) con los datos calculados: base imponible, tipo impositivo, cuota íntegra, deducciones, pagos a cuenta, cuota diferencial y bloques del modelo (datos del declarante, resultado contable, ajustes, base, cuota). La presentación telemática queda fuera de alcance.
- **Rationale**: Cumple FR-006 y la assumption del spec; la generación del soporte es suficiente para MVP.
- **Alternatives considered**: Integración AEAT telemática (excesiva complejidad y dependencia de certificados digitales).

## D9. Validación de consistencia del modelo 200

- **Decision**: Antes de exportar, el sistema valida: (1) base imponible = resultado + ajustes; (2) cuota = base × tipo - deducciones; (3) cuota diferencial = cuota - pagos a cuenta; (4) todos los importes >= 0 cuando corresponda. Si alguna validación falla → 422 con detalle del error.
- **Rationale**: Cumple el escenario de aceptación 2 del US3 del spec.
- **Alternatives considered**: Sin validación (riesgo de errores en la declaración).

## D10. Multi-tenancy y auditoría del cálculo

- **Decision**: Cada cálculo de IS se persiste con `empresa_id` derivado de la sesión autenticada, en la misma transacción ACID. Se registra audit log (actor, timestamp UTC, IP, acción, payload como strings `Decimal`). El `empresa_id` nunca se envía en el body del request. El cálculo y el asiento se crean en la misma transacción.
- **Rationale**: Cumple constituciones III y auditoría inmutable.
- **Alternatives considered**: Audit log en tabla separada con commit independiente (rompe atomicidad).
