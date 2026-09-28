# API Contracts: Medios de Pago y Efectos (SPEC-021)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Estilo: REST bajo `/api/v1` (todos los endpoints exigen la cabecera de empresa activa derivada de sesión; la empresa activa se deriva exclusivamente de la sesión, nunca del path). Respuestas JSON; importes como strings decimales (p. ej. `"123.4500"`), nunca números de coma flotante.

## Efectos (Cartera)

### POST `/api/v1/efectos`
Registrar un efecto (cheque, pagaré, letra) con vencimiento.
- Body: `{ "tercero_id": "<uuid>", "tipo_efecto": "CHEQUE|PAGARE|LETRA", "numero_documento": "string", "fecha_emision": "YYYY-MM-DD", "fecha_vencimiento": "YYYY-MM-DD", "importe": "1500.0000", "notas"?: "string" }`
- Reglas: `fecha_vencimiento >= fecha_emision`; ejercicio abierto; unicidad documento por tercero+tipo.
- 201: `{ "id", "numero_documento", "estado": "emitido", "importe", "fecha_vencimiento" }`
- 409: ejercicio cerrado, documento duplicado.
- 422: validación de campos.

### GET `/api/v1/efectos`
Cartera de efectos con filtros: `estado` (emitido/cobrado/impagado), `tipo_efecto`, `tercero_id`, `fecha_vencimiento[gte/lte]`, paginación.
- 200: `{ "items": [{ "id", "tercero_id", "tercero_nombre", "tipo_efecto", "numero_documento", "fecha_emision", "fecha_vencimiento", "importe", "estado" }], "total" }`

### GET `/api/v1/efectos/{id}`
Detalle de un efecto con su historial de estados y asientos asociados.
- 404 si no pertenece a la empresa activa.

### POST `/api/v1/efectos/{id}/cobrar`
Liquidar un efecto al cobro (genera asiento balanceado).
- Body: `{ "fecha_cobro": "YYYY-MM-DD", "cuenta_banco": "5720000" }`
- Reglas: efecto en estado `emitido`; ejercicio abierto. Asiento: Debe 572 (importe) | Haber 431 (importe). Si hay comisión, usar endpoint cobro_medio.
- 200: `{ "estado": "cobrado", "asiento_cobro_id" }`
- 409: efecto no está en estado `emitido`, ejercicio cerrado.
- 422: fecha_cobro inválida.

### POST `/api/v1/efectos/{id}/impago`
Registrar impago de un efecto (genera REVERSAL y reapertura del vencimiento).
- Body: `{ "fecha_impago": "YYYY-MM-DD", "motivo"?: "string", "gastos_devolucion"?: "0.0000" }`
- Reglas: efecto en estado `emitido`; ejercicio abierto. Asiento REVERSAL: Debe 431 (importe) + 626 (gastos si > 0) | Haber 572/570 (importe + gastos). Reapertura del vencimiento (SPEC-011) a `pendiente`.
- 200: `{ "estado": "impagado", "asiento_impago_id" }`
- 409: efecto no está en estado `emitido`, ejercicio cerrado.

## Cobros por Medio (TPV/Tarjeta/Transferencia)

### POST `/api/v1/cobros-medio`
Registrar un cobro por TPV, tarjeta o transferencia contra un vencimiento.
- Body: `{ "vencimiento_id": "<uuid>", "medio_cobro": "TARJETA|TRANSFERENCIA|CAJA", "fecha_cobro": "YYYY-MM-DD", "cuenta_banco": "5720000", "importe_comision"?: "0.0000" }`
- Reglas: vencimiento `pendiente`; ejercicio abierto; `importe_comision >= 0` y `<= importe_total`. Asiento: Debe 572 (neto) + 626 (comisión si > 0) | Haber 430 (total).
- 201: `{ "id", "medio_cobro", "importe_neto", "importe_comision", "asiento_cobro_id" }`
- 409: vencimiento no está pendiente, ejercicio cerrado.
- 422: comisión supera importe total.

### GET `/api/v1/cobros-medio`
Listado de cobros por medio con filtros: `medio_cobro`, `fecha_cobro[gte/lte]`, `tercero_id`, paginación.
- 200: `{ "items": [{ "id", "vencimiento_id", "medio_cobro", "fecha_cobro", "importe_total", "importe_comision", "importe_neto", "asiento_cobro_id" }], "total" }`

### GET `/api/v1/cobros-medio/{id}`
Detalle de un cobro con su asiento y desglose de comisiones.
- 404 si no pertenece a la empresa activa.

## Tratamiento de errores

- `401/403`: autenticación/permisos (SPEC-003).
- `404`: recurso inexistente en la empresa activa (nunca filtra datos de otra empresa).
- `409`: conflicto de estado (ejercicio cerrado, efecto ya cobrado/impagado, documento duplicado, vencimiento ya liquidado).
- `422`: validación de negocio (importes, fechas, comisiones).
- Errores de importes siempre en precisión decimal; el backend es el único que valida partida doble.
