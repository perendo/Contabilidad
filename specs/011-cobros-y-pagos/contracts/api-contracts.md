# API Contracts: Vencimientos, Cobros y Pagos (SPEC-011)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Estilo: REST bajo `/api/v1/...` (empresa activa derivada de sesion en cabecera; `empresa_id` nunca en body/path como dato de seleccion). Respuestas JSON; importes como strings decimales (p. ej. `"123.4500"`), nunca numeros de coma flotante.

## Vencimientos

### GET `/api/v1/vencimientos`
Listado paginado de vencimientos con filtros `estado`, `tipo` (cobro/pago), `tercero_id`, `factura_id`, `fecha[gte/lte]`.
- 200: `{ "items": [{ "id", "numero_vencimiento", "fecha_vencimiento", "importe", "acumulado", "saldo_pendiente", "estado", "tercero_id" }], "total" }`

### GET `/api/v1/vencimientos/{id}`
Detalle de vencimiento con sus cobros/pagos.
- 404 si no pertenece a la empresa activa.

### POST `/api/v1/vencimientos`
Garantizar la creacion de vencimientos (normalmente llegan de SPEC-007; endpoint disponible por si la factura no los genera en primeras fases).
- Body: `{ "factura_id", "tipo": "cobro|pago", "fecha_vencimiento", "importe" }`
- 201: `{ "vencimiento_id", "numero_vencimiento", "saldo_pendiente" }`
- 409: `ejercicio_cerrado` si la fecha cae en ejercicio cerrado.

## Cobros y Pagos

### POST `/api/v1/vencimientos/{id}/cobrar`
Registrar un cobro total o parcial del vencimiento.
- Body: `{ "fecha": "YYYY-MM-DD", "importe": "100.0000", "cuenta_tesoreria": "5720000" }`
- Reglas: valida el ejercicio abierto; crea `CobroPago` + asiento `JournalEntry` (Debe 572/570 | Haber 430) en la misma transaccion ACID; actualiza `acumulado` y estado.
- 200: `{ "cobro_id", "estado": "parcial|cobrado", "saldo_pendiente", "journal_entry_id" }`
- 422: `exceso_importe` (importe > saldo pendiente), `importe_invalido`.
- 409: `ejercicio_cerrado`, `vencimiento_saldado` (no puede volver a cobrarse), `vencimiento_remesado` (cobro directo no permitido mientras esta en remesa emitida).

### POST `/api/v1/vencimientos/{id}/pagar`
Registrar un pago total o parcial del vencimiento (proveedores).
- Body: `{ "fecha": "YYYY-MM-DD", "importe": "100.0000", "cuenta_tesoreria": "5720000" }`
- Reglas identicas; asiento: Debe 400 | Haber 572/570.
- 200/422/409 como en cobrar.

### GET `/api/v1/vencimientos/{id}/cobros`
Historial de cobros/pagos del vencimiento con sus asientos.
- 200: `{ "items": [{ "cobro_id", "fecha", "importe", "tipo", "journal_entry_id" }] }`

## Remesas (agrupacion y estado)

### POST `/api/v1/remesas`
Crear remesa de agrupacion de vencimientos (borrador).
- Body: `{ "tipo": "cobro|pago", "fecha_cargo_prevista": "YYYY-MM-DD" | null, "vencimiento_ids": ["<uuid>", ...] }`
- Reglas: solo vencimientos `pendiente`/`parcial` de la empresa activa; asigna `numero_remesa` correlativo (empresa+ejercicio); calcula `importe_total`.
- 201: `{ "remesa_id", "numero_remesa", "estado": "borrador", "n_vencimientos", "importe_total" }`
- 409: `ejercicio_cerrado`, `vencimiento_ya_remesado`.
- 422: `vencimiento_no_remesable` (cobrado/saldado/sin saldo pendiente).

### GET `/api/v1/remesas`
Listado de remesas con filtros `estado`, `tipo`, `ejercicio`, paginacion.
- 200: `{ "items": [{ "id", "numero_remesa", "tipo", "estado", "n_vencimientos", "importe_total" }], "total" }`

### GET `/api/v1/remesas/{id}`
Detalle de remesa con sus vencimientos miembros y estados.
- 404 si no pertenece a la empresa activa.

### POST `/api/v1/remesas/{id}/emitir`
Marcar la remesa como emitida (pasa sus vencimientos a `remesado`). **No genera fichero**: la publicacion del fichero SEPA/CSB 19.19 se cubre en SPEC-020.
- Body: `{ "fecha_emision": "YYYY-MM-DD" }`
- 200: `{ "remesa_id", "estado": "emitida", "n_vencimientos_remesados" }`
- 409: `ya_emitida` (idempotencia), `ejercicio_cerrado`.

### DELETE `/api/v1/remesas/{id}`
Eliminar una remesa en estado `borrador` (los vencimientos vuelven a `pendiente`).
- 200: `{ "remesa_id", "estado": "cancelada" }`
- 409: `remesa_emitida` (no se puede borrar una emitida; gestionar por SPEC-020/013).

## Informe de Antiguedad

### GET `/api/v1/antiguedad`
Informe de antiguedad de saldos a fecha de consulta.
- Query params: `tipo=tercero` (default), `fecha_a=YYYY-MM-DD` (default hoy), `tercero_id` filtrar, `rango` para filtrar por rango.
- 200: `{ "fecha_corte": "2026-09-16", "items": [{ "tercero_id", "saldo_total_pendiente", "rango_30", "rango_60", "rango_90", "rango_90mas", "vencimientos": [...] }], "total_saldo": "0.0000" }`
- Validacion: suma de rangos == saldo_total_pendiente en backend; 422 si no cuadra (defensivo).

## Tratamiento de errores

- `401/403`: autenticacion/permisos (SPEC-003).
- `404`: recurso inexistente en la empresa activa (siempre filtra por empresa).
- `409`: conflicto de estado (ejercicio cerrado, vencimiento saldado/remesado, remesa emitida).
- `422`: validacion de negocio (exceso de importe, importe invalido).
- Orro de importes siempre en precision decimal; el backend es el unico que valida partida doble.