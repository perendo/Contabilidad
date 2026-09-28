# Research: Libros de IVA y Modelos Fiscales (SPEC-012)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Resoluciones de los unknowns del Technical Context y decisiones de diseno conforme a la constitucion y al plan raiz.

## D1. Construccion automatica de los libros de IVA

- **Decision**: Los libros de IVA (emitidas, recibidas, intracomunitarias) se reconstruyen bajo demanda a partir de las facturas (SPEC-007) y de los asientos vinculados (SPEC-002). Cada linea del libro se deriva de una factura con su base (481/472), cuota (477/472) y tipo; nunca se permite entrada manual.
- **Rationale**: FR-001; garantiza que el registro fiscal es un derivado del contable, sin duplicidad de datos.
- **Alternatives considered**: Tabla de libro poblada por eventos de facturacion (duplica estado y puede desincronizarse); entrada manual (prohibida por la spec).

## D2. Periodo fiscal y trimestralidad/mensualidad

- **Decision**: Un periodo fiscal se define por (empresa, ejercicio, tipo 303)`TRIMESTRE` o `MES` configurable por empresa segun su regimen (mensual grandes empresas/inscripcion SII, trimestral por defecto). Los libros y modelos se consultan por periodo; el 303 se calcula por periodo.
- **Rationale**: FR-002; la mensualidad es obligatoria para empresas SII; la trimestralidad es el regimen general.
- **Alternatives considered**: Solo trimestral (incumple grandes empresas); periodo fijo no configurable (rigidez).

## D3. Calculo del modelo 303 con cuadre con libros

- **Decision**: El 303 agrega por periodo: devengado (base y cuota de emitidas, por tipo) y deducible (recibidas, por tipo). Resultado = cuota devengada - cuota deducible (+ cuotas de rectificaciones). El cuadre con los libros se verifica en backend: si las bases/cuotas difieren de los libros del periodo -> 422 `descuadre_libros`.
- **Rationale**: FR-002 y SC-002. Defensivo ante desincronizaciones.
- **Alternatives considered**: Calcular desde tablas de resumen (posible descuadre silencioso).

## D4. Modelo 347 y 349

- **Decision**: El 347 (resumen anual de operaciones con terceros) agrega por NIF y clave operacional las operaciones > 3.005,06 EUR anuales (limite legal), con importe acumulado del ejercicio. El 349 (intracomunitarias) agrega por NIF del periodo las operaciones intracomunitarias con detalle de bienes/servicios. Ambos se preparan a partir del libro correspondiente.
- **Rationale**: FR-003; el 347 se calcula sobre el ejercicio completo; el 349 sobre el periodo declarado (trimestre/mes).
- **Alternatives considered**: 347 mensual (no es legal); agregar 347 dentro del 303 (son modelos distintos).

## D5. Exportacion de modelos y trazabilidad

- **Decision**: Los modelos se exportan como fichero (JSON + CSV + XML de presentacion AEAT para 303/349; informe HTML/PDF legible para 347) con identificacion de periodo, empresa (NIF) y numeracion de exportacion correlativa por (empresa, ejercicio). Cada exportacion se registra en `ExportacionModelo` con usuario, fecha UTC y hash; regenerar un periodo ya exportado exige advertencia y queda trazado.
- **Rationale**: FR-004/FR-006; reduccion de errores de transcripcion y trazabilidad legal.
- **Alternatives considered**: Regeneracion silenciosa de ficheros (pierde trazabilidad del periodo exportado).

## D6. Recargo de equivalencia

- **Decision**: Las cuotas de recargo se registran en el libro como importe separado del IVA general, con su propia cuenta contable (configurable por empresa, tipicamente 477/... de recargo). El 303 las presenta en las casillas de recargo correspondientes (casillas especificas del modelo).
- **Rationale**: FR-009; el recargo es una cuota adicional al IVA para minoristas, con casillas propias en el 303.
- **Alternatives considered**: Sumar recargo al IVA general (mezcla cuotas y rompe el 303).

## D7. Criterio de caja

- **Decision**: Para empresas acogidas al criterio de caja (opcional), el IVA de una factura (emitida/recibida) queda DIFFERIDO hasta el cobro/pago efectivo, trazado en una tabla de IVA diferido enlazada al vencimiento (SPEC-011). El IVA diferido entra en el 303 del periodo en que ocurre el cobro/pago (momento del devengo real).
- **Rationale**: FR-010; el vencimiento de SPEC-011 es la fuente del cobro/pago que activa el devengo.
- **Alternatives considered**: Devengo inmediato para todos (incumple el regimen); trackear manualmente (pierde trazabilidad).

## D8. Interfaz SII (opcional, habilitable por empresa)

- **Decision**: El SII queda declarado como configuracion por empresa (habilitado/deshabilitado) con mapeo a los esquemas XML de SuministroInmediatoInformacion (`SuministroLrFacturasEmitidas/Recibidas`) y a sus operaciones. En esta feature NO se ejecuta envio: solo se expone la interfaz y la generacion del XML pendiente; la presentacion ejecutada se integra con SPEC-029 (export integral).
- **Rationale**: FR-007/FR-011; respeta el edge case ''SII si la empresa aun no esta obligada'' manteniendo la interfaz lista.
- **Alternatives considered**: Envio SII real en esta feature (amplia alcance y duplica SPEC-029); sin interfaz (pierde la preparacion).

## D9. Aislamiento multi-tenant en fiscal

- **Decision**: `empresa_id` se deriva de sesion en todas las consultas de libros, periodos, modelos, exportaciones y configuracion de regimenes. pruebas de integracion demuestran que empresa B no ve los libros/modelos de A.
- **Rationale**: FR-005 / constitucion III.
- **Alternatives considered**: empresa_id en body (prohibido).

## D10. Precision decimal y limites legales

- **Decision**: Bases, cuotas, recargo, diferidos y resultados del 303 en `Decimal`/`NUMERIC(18,4)`. Los limites legales (3.005,06 EUR del 347) se comparan con Decimal exacto. El redondeo de importes en el fichero AEAT se hace con la regla legal (2 decimales, al centimo mas cercano) sin perdida en el almacenamiento.
- **Rationale**: FR-008 y SC-005.
- **Alternatives considered**: Redondeo a 2 decimales en almacen (pierde 4-d decimal en asientos y libros).