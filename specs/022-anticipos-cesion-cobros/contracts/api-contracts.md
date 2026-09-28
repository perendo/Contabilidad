# API Contracts: Anticipos, Fondos a Cuenta y Cesión de Cobros (SPEC-022)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Estilo: REST bajo `/api/v1` (todos los endpoints exigen la cabecera de empresa activa derivada de sesión; la empresa activa se deriva exclusivamente de la sesión, nunca del path). Respuestas JSON; importes como strings decimales (p. ej. `"123.4500"`), nunca números de coma flotante.

## Anticipos de Clientes y Proveedores

### POST `/api/v1/anticipos`
Registrar un anticipo de cliente o proveedor.
- Body: `{ "tercero_id": "<uuid>", "tipo": "CLIENTE|PROVEEDOR", "fecha": "YYYY-MM-DD", "importe": "5000.0000", "concepto": "string", "cuenta_contable"?: "438|407|408" }`
- Reglas: ejercicio abierto en `fecha`; cuenta contable según tipo (438 para CLIENTE, 407/408 para PROVEEDOR). Asiento: Debe 572 (CLIENTE) o 407/408 (PROVEEDOR) | Haber 438 (CLIENTE) o 572 (PROVEEDOR).
- 201: `{ "id", "tipo", "importe", "saldo_pendiente", "asiento_id" }`
- 409: ejercicio cerrado.
- 422: validación de campos.

### GET `/api/v1/anticipos`
Listado de anticipos con filtros: `tipo`, `tercero_id`, `estado` (pendiente/parcial/total), `fecha[gte/lte]`, paginación.
- 200: `{ "items": [{ "id", "tercero_id", "tercero_nombre", "tipo", "fecha", "importe", "saldo_pendiente", "estado", "asiento_id" }], "total" }`

### GET `/api/v1/anticipos/{id}`
Detalle de anticipo con sus liquidaciones y saldo.
- 404 si no pertenece a la empresa activa.

### GET `/api/v1/anticipos/{id}/liquidaciones`
Historial de liquidaciones de un anticipo.
- 200: lista de liquidaciones con factura, importe y fecha.

## Liquidación de Anticipos

### POST `/api/v1/anticipos/{id}/liquidar`
Aplicar un anticipo contra una o varias facturas.
- Body: `{ "aplicaciones": [{ "factura_id": "<uuid>", "importe_aplicado": "2000.0000" }], "fecha_aplicacion": "YYYY-MM-DD" }`
- Reglas: suma de importes_aplicados <= saldo_pendiente del anticipo; ejercicio abierto; facturas de la misma empresa. Asiento por cada aplicación: Debe 430/410 (factura) | Haber 438/407 (anticipo). El saldo se actualiza atómicamente.
- 200: `{ "anticipo_id", "saldo_pendiente", "liquidaciones_creadas": n }`
- 409: ejercicio cerrado, saldo insuficiente.
- 422: importe supera saldo, factura no encontrada.

## Cesión de Cobros (Factoring/Confirming)

### POST `/api/v1/cesiones`
Crear una cesión de cobros con sus vencimientos.
- Body: `{ "entidad_financiera": "string", "fecha_cesion": "YYYY-MM-DD", "vencimiento_ids": ["<uuid>", ...], "comision": "150.0000", "tipo_comision": "IMPORTE_FIJO|PORCENTAJE" }`
- Reglas: todos los vencimientos en estado `pendiente`; ejercicio abierto; al menos un vencimiento. Asiento: Debe 572 (neto recibido) + 662 (comisión) | Haber 430 (total cedido). Vencimientos pasan a `cedido`.
- 201: `{ "id", "entidad_financiera", "importe_total_cedido", "comision", "importe_neto_recibido", "asiento_id", "n_vencimientos" }`
- 409: ejercicio cerrado, algún vencimiento no pendiente.
- 422: sin vencimientos, comisión inválida.

### GET `/api/v1/cesiones`
Listado de cesiones con filtros: `estado`, `entidad_financiera`, `fecha_cesion[gte/lte]`, paginación.
- 200: `{ "items": [{ "id", "entidad_financiera", "fecha_cesion", "importe_total_cedido", "comision", "estado", "n_vencimientos" }], "total" }`

### GET `/api/v1/cesiones/{id}`
Detalle de cesión con sus vencimientos incluidos y notificaciones.
- 404 si no pertenece a la empresa activa.

### POST `/api/v1/cesiones/{id}/notificar`
Registrar notificación al cliente sobre la cesión.
- Body: `{ "cliente_id": "<uuid>", "medio": "EMAIL|CORREO|REGISTRO", "fecha_notificacion": "YYYY-MM-DD" }`
- 200: `{ "notificacion_id", "estado": "enviada" }`
- 422: cliente no asociado a vencimientos de la cesión.

### POST `/api/v1/cesiones/{id}/saldar`
Saldar la cesión cuando la entidad cobra al cliente (cierra la operación).
- Body: `{ "fecha_saldado": "YYYY-MM-DD" }`
- Reglas: cesión en estado `activa`; todos los vencimientos saldados por la entidad. Cambia estado a `saldada`.
- 200: `{ "estado": "saldada" }`
- 409: cesión no activa.

## Tratamiento de errores

- `401/403`: autenticación/permisos (SPEC-003).
- `404`: recurso inexistente en la empresa activa (nunca filtra datos de otra empresa).
- `409`: conflicto de estado (ejercicio cerrado, vencimiento ya cedido/saldado, saldo insuficiente).
- `422`: validación de negocio (importes, fechas, vencimientos no elegibles).
- Errores de importes siempre en precisión decimal; el backend es el único que valida partida doble.
