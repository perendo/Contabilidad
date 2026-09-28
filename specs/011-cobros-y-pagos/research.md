# Research: Vencimientos, Cobros y Pagos (SPEC-011)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Resoluciones de los unknowns del Technical Context y decisiones de diseno conforme a la constitucion y al plan raiz.

## D1. Estados de vencimiento

- **Decision**: Un vencimiento tiene estados `pendiente`, `parcial`, `cobrado` y `remesado` (incluido en una remesa con estado emitida). El estado `parcial` refleja que hay cobros/pagos acumulados sin llegar al importe total. El vencimiento se salda unicamente cuando el acumulado == importe.
- **Rationale**: FR-002; los estados alimentan remesas (SPEC-020) y antiguedad.
- **Alternatives considered**: Solo `pendiente/cobrado` sin parcial (impide gestion de pagos a plazos).

## D2. Asiento de cobro/pago

- **Decision**: Cada cobro registrado genera un `JournalEntry` por la diferencia contra la cuenta de tesoreria configurada por empresa (572 banco o 570 caja, por vencimiento). Para facturas de venta: Debe 572/570 | Haber 430 (clientes). Para compras: Debe 400 (proveedores) | Haber 572/570. Si hay descuento por pronto pago, se trata en SPEC-020.
- **Rationale**: FR-003; el asiento se crea en la misma transaccion ACID que el cobro (atomicidad con el motor de asientos SPEC-002).
- **Alternatives considered**: Asiento separado y desvinculado (pierde atomicidad); direccion manual de cuenta en cada cobro (duplica configuracion).

## D3. Acumulacion de parciales y cierre

- **Decision**: `acumulado = suma(cobros_pagos)`. Al registrar un parcial se valida `acumulado + importe_nuevo <= importe_vencimiento`; si `<` pasa a `parcial`; si `==` pasa a `cobrado`; si `>` se rechaza 422 `exceso_importe`. La precision es Decimal con 4 decimales: el cierre requiere igualdad exacta.
- **Rationale**: FR-004; evita pagos en exceso y cierres con redondeo.
- **Alternatives considered**: Redondeo intermediario (descubre diferencias de centimos).

## D4. Remesas de agrupacion (alcance recortado)

- **Decision**: La remesa en SPEC-011 es SOLO la agrupacion de vencimientos con estado y trazabilidad (`remesa` -> vencimientos miembro, estados `borrador`/`emitida`). La generacion de ficheros de domiciliacion SEPA/CSB 19.19, validacion de plazos y mandatos se cubre en SPEC-020.
- **Rationale**: RE-SCOPING de la especificacion 2026-09-16; evita duplicidad con SPEC-020 y mantiene 011 como gestion de tesoreria.
- **Alternatives considered**: SEPA dentro de 011 (duplicidad con 020); sin remesas en 011 (020 quedaria huertano).

## D5. Informe de antiguedad de saldos

- **Decision**: La antiguedad clasifica el saldo pendiente de un tercero por rangos a la fecha de consulta: `<30`, `30-60`, `60-90`, `>90` dias desde la fecha de vencimiento, para vencimientos no saldados. Saldo por rango = suma de importes pendientes de vencimientos en dicho rango.
- **Rationale**: FR-006; mide morosidad y alimenta provisiones/analisis crediticio.
- **Alternatives considered**: Antiguedad sobre factura en vez de vencimiento (mezcla vencimientos distintos); solo listado (sin totales por rango).

## D6. Bloqueo de ejercicio cerrado

- **Decision**: Antes de registrar cualquier cobro/pago/cambio de estado, se valida que el ejercicio de la fecha del asiento este `abierto` (o `con_apertura` pero no `cerrado`). Si el ejercicio esta cerrado -> 409 `ejercicio_cerrado` y la operacion se descarta.
- **Rationale**: FR-007 (constitucion: operaciones rechazadas en ejercicios cerrados).
- **Alternatives considered**: Permitir con permiso especial (rompe la garantia de cierre).

## D7. Multi-tenancy de tesoreria

- **Decision**: `empresa_id` se deriva exclusivamente del contexto autenticado; todas las queries de vencimientos, cobros, remesas y antiguedad filtran por el. pruebas de integracion demuestran que empresa B no ve ni opera sobre datos de A.
- **Rationale**: Constitucion III.
- **Alternatives considered**: empresa_id en body (prohibido).

## D8. Correlatividad de operaciones

- **Decision**: Se asigna numero correlativo de operacion por (empresa_id, ejercicio) dentro de la misma transaccion ACID con `SELECT ... FOR UPDATE` sobre el contador de secuencia. Se mantiene la correlatividad de vencimientos cuando procede.
- **Rationale**: Constitucion IV.
- **Alternatives considered**: UUID sin numero de operacion (perdida de trazabilidad legal).

## D9. Rectificativas y recalculo de vencimientos

- **Decision**: Cuando una factura rectificativa (SPEC-007) ajusta una factura, los vencimientos se recalculan: se anula (REVERSAL enlazado) el vencimiento original pendiente y se generan nuevos vencimientos por la diferencia/importe corregido. El asiento de la rectificativa lo emite SPEC-007; esta feature solo reasocia vencimientos.
- **Rationale**: Edge case del spec; mantiene la coherencia entre importe de factura y vencimientos.
- **Alternatives considered**: Ajuste in-place del importe (pierde trazabilidad del historico de vencimientos).

## D10. Precision decimal en todo el flujo

- **Decision**: Todos los importes (vencimientos, cobros, acumulados, saldos de antiguedad) se calculan y almacenan en `Decimal`/`NUMERIC(18,4)`. Los tests cubren casos de redondeo (p. ej., 1/3 de un importe con 3 parciales) verificando que la suma de parciales == importe exacto sin desviaciones de coma flotante.
- **Rationale**: FR-008 / constitucion de precision.
- **Alternatives considered**: Aritmetica float (prohibido).