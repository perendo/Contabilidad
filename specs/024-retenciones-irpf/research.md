# Research: Retenciones IRPF y Modelos 111/115/190 (SPEC-024)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Resoluciones de los unknowns del Technical Context y decisiones de diseño conforme a la constitución y al plan raíz.

## D1. Fuente de retenciones (acumulación)

- **Decision**: Las retenciones se obtienen de las **facturas con retención de SPEC-007** (retención IRPF en facturas de proveedores) y de **alquileres con retención** (modelo 115). El sistema acumula por `empresa_id`, `trimestre` (natural: Q1=ene-mar, Q2=abr-jun, Q3=jul-sep, Q4=oct-dic) y `tercero_id`. No se almacenan como datos separados; se calculan en tiempo de consulta a partir del submayor de retenciones de las facturas.
- **Rationale**: La fuente de verdad es el diario contable de facturación (SPEC-007); duplicar crea riesgo de desincronización.
- **Alternatives considered**: Tabla de retenciones que se sincroniza manualmente (excesiva complejidad y riesgo de error).

## D2. Cuenta 4751 (retenciones y ingresos a cuenta)

- **Decision**: La cuenta **4751** (Hacienda Pública, acreedora por retenciones e ingresos a cuenta) es la cuenta de acumulación de retenciones. Las retenciones de proveedores se registran como Debe 4751 | Haber 572 al liquidarse. La liquidación trimestral genera: Debe 4751 (acumulado) | Haber 572 (ingreso en banco). El saldo de 4751 a final de trimestre debe ser cero tras la liquidación.
- **Rationale**: Cuenta estándar del PGC español para retenciones e ingresos a cuenta.
- **Alternatives considered**: Usar 473 en lugar de 4751 (confunde con pagos a cuenta del IS); 4751 separada por tipo de retención (excesiva fragmentación).

## D3. Modelo 111 — autoliquidación trimestral

- **Decision**: El modelo 111 se genera como **informe/descargable** con los datos acumulados del trimestre: perceptores con retención, importes totales, tipo de retención, cuota a ingresar. La presentación telemática queda fuera de alcance. El modelo incluye: datos del declarante, periodo (trimestre), detalle por perceptor (NIF, nombre, actividad, base, tipo, cuota) y totales.
- **Rationale**: Cumple el escenario de aceptación del US1 del spec; la generación del soporte es suficiente para MVP.
- **Alternatives considered**: Integración AEAT telemática (excesiva complejidad y dependencia de certificados digitales).

## D4. Modelo 115 — arrendamientos con retención

- **Decision**: El modelo 115 es idéntico en estructura al 111 pero filtrado por **retenciones de arrendamientos** (alquileres). Se genera a partir de las facturas de alquiler con retención del periodo. El modelo se almacena como entidad separada `Modelo115`.
- **Rationale**: Especificación del spec (T-03, FR-003).
- **Alternatives considered**: Unificar 111 y 115 en un solo modelo con filtro (dificulta la generación por separado y la trazabilidad).

## D5. Liquidación trimestral (asiento 4751 vs 572)

- **Decision**: La liquidación genera un asiento **Debe 4751** (acumulado del trimestre) | **Haber 572** (ingreso en banco). El asiento se crea en la misma transacción que la marca del periodo como `liquidado`. El saldo de 4751 queda a cero para el trimestre siguiente. Si hay saldo deudor (retenciones a compensar), se informa pero no se genera asiento de ingreso.
- **Rationale**: Cumple FR-004 y US2 del spec; el cuadre contable de 4751 es obligatorio.
- **Alternatives considered**: Liquidación sin asiento (deja el 4751 sin cuadrar); asiento parcial (pierde atomicidad).

## D6. Modelo 190 — declaración anual por perceptor

- **Decision**: El modelo 190 se genera como **informe/descargable** con el resumen anual de retenciones e ingresos a cuenta por perceptor (tercero). Agrupa las retenciones trimestrales del 111 por perceptor y año. **NIF obligatorio**: los perceptores sin NIF configurado se bloquean del 190 y se reportan como errores. El modelo incluye: datos del declarante, año, detalle por perceptor (NIF, nombre, actividades, perceptiones) y totales.
- **Rationale**: Cumple FR-005 y US3 del spec; la declaración anual es obligatoria para Hacienda.
- **Alternatives considered**: Generar 190 automáticamente desde 111 acumulados (excesiva complejidad de agregación); sin validación NIF (incumple requisito legal).

## D7. Rectificativas y recálculo de retenciones

- **Decision**: Cuando se emite una factura rectificativa (SPEC-007), el sistema recalcula la retención del periodo afectado: la retención de la factura original se sustituye por la de la rectificativa. El recalculo se ejecuta de forma automática en el servicio de facturación y se refleja en la acumulación del modelo 111/190.
- **Rationale**: Cumple FR-006 del spec; la rectificativa modifica la base y la retención del periodo.
- **Alternatives considered**: Recálculo manual (riesgo de olvido); rectificativa como línea separada (duplica el efecto en el modelo).

## D8. Configuración de tipos de retención

- **Decision**: Los tipos de retención se configuran por **empresa** y **régimen** (general, arrendamiento) con **vigencia** temporal. Ejemplo: tipo general 19%, arrendamientos 19%, profesionales 15%. Se almacenan en `ConfiguracionRetencion` por `empresa_id`, `regimen`, `tipo_porcentaje`, `fecha_desde`, `fecha_hasta`.
- **Rationale**: Los tipos pueden cambiar por reformas fiscales; distintos regímenes tienen distintos tipos.
- **Alternatives considered**: Tipo fijo hardcodeado (no realista); tipo calculado automáticamente (excesiva complejidad).

## D9. Periodo de autoliquidación

- **Decision**: La autoliquidación es por **trimestre natural** (Q1: ene-mar, Q2: abr-jun, Q3: jul-sep, Q4: oct-dic). El sistema calcula automáticamente el trimestre a partir de las fechas de las facturas. Un trimestre se marca como `liquidado` al generar la liquidación; el modelo 111/115 se genera para ese trimestre liquidado.
- **Rationale**: Es el régimen de autoliquidación trimestral de IRPF (art. 82 Reglamento IRPF).
- **Alternatives considered**: Trimestres artificiales (no realista); mensual (excesiva frecuencia).

## D10. Validación de NIF para modelo 190

- **Decision**: Antes de generar el modelo 190, el sistema valida que todos los perceptores incluidos tengan **NIF configurado** en el maestro de terceros (SPEC-008). Si algún perceptor no tiene NIF → 422 con lista de perceptores incompletos. El modelo no se genera hasta que se resuelva.
- **Rationale**: El NIF es obligatorio para la declaración anual; sin él, el modelo es rechazado por Hacienda.
- **Alternatives considered**: Generar el modelo sin NIF y reportar errores (incumple el requisito); NIF opcional con advertencia (incumple la normativa).
