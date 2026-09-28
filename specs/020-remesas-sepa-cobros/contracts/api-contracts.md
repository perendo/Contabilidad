# API Contracts: Remesas SEPA y Soporte Magnético (SPEC-020)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Estilo: REST bajo `/api/v1` (todos los endpoints exigen la cabecera de empresa activa derivada de sesión; la empresa activa se deriva exclusivamente de la sesión, nunca del path). Respuestas JSON; importes como strings decimales (p. ej. `"123.4500"`), nunca números de coma flotante.

## Remesas

### POST `/api/v1/remesas`
Crear remesa en estado `borrador` a partir de una selección de recibos.
- Body: `{ "formato": "SEPA_DD" | "CSB_19_19", "tipo_adeudo": "CORE" | "B2B", "recibo_ids": ["<vencimiento_id>", ...] }`; la fecha de cargo se deriva de cada vencimiento.
- Reglas: admite recibos pendientes vencidos o futuros del ejercicio abierto; no incluye recibos cobrados o sin IBAN; asigna `numero_remesa` correlativo (empresa+ejercicio), conserva la fecha de cada recibo y calcula `importe_total`.
- 201: `{ "id", "numero_remesa", "estado": "borrador", "importe_total", "n_recibos" }`
- 422: lista de recibos excluidos con motivo (`sin_iban`, `ya_cobrado`, `ejercicio_cerrado`, `sin_mandato_b2b`, `plazo_presentacion`).

### POST `/api/v1/remesas/{id}/emitir`
Emitir la remesa (genera el fichero y pasa a `emitida`). Requiere `borrador`.
- Reglas: valida plazos SEPA (CORE D-2 / B2B D-1 hábiles), mandatos B2B, y persiste `BlobFichero` con `sha256`.
- 200: `{ "estado": "emitida", "numero_remesa", "grupos_fecha": [{ "fecha_cargo", "n_recibos", "importe_total" }], "fichero": { "id", "tipo", "sha256", "fecha_emision" } }`
- 409: si la remesa ya fue emitida (idempotencia: no se regenera).

### GET `/api/v1/remesas`
Listado con filtros `estado`, `ejercicio`, `formato`, `fecha_cargo[gte/lte]`, paginación.
- 200: `{ "items": [{ "id", "numero_remesa", "ejercicio", "fecha_cargo", "formato", "importe_total", "estado" }], "total" }`

### GET `/api/v1/remesas/{id}`
Detalle de remesa con sus recibos (vencimiento, tercero, IBAN, importe, estado) y devoluciones asociadas.
- 404 si no pertenece a la empresa activa.

### GET `/api/v1/remesas/{id}/fichero`
Descarga del fichero generado (`content-disposition` con el nombre `RE_{prefijoEmpresa}{numero:06}_{CCYYMMDD}.{xml|1919}`). 404 si aún no emitida.

### POST `/api/v1/remesas/{id}/recibos/{recibo_id}/cobrar`
Confirmación manual de cobro del recibo.
- Body: `{ "fecha_cobro": "YYYY-MM-DD", "cuenta": "5720000" }`
- 200: `{ "estado": "cobrado", "asiento_cobro_id" }` (si el cobro requiere asiento de SPEC-011, se crea balanceado).
- 409: si el recibo ya está cobrado o existe otro cobro confirmado para el mismo vencimiento.

### POST `/api/v1/remesas/{id}/recibos/{recibo_id}/conciliar`

Confirmación de cobro recibida desde SPEC-013. El evento debe incluir un identificador único del movimiento bancario.
- Body: `{ "movimiento_id": "<uuid>", "fecha_cobro": "YYYY-MM-DD", "cuenta": "5720000" }`
- 200: `{ "estado": "cobrado", "asiento_cobro_id", "idempotente": false }`
- 200 idempotente: devuelve el mismo asiento con `idempotente=true` si el mismo movimiento ya fue procesado.
- 409: si el recibo está devuelto o el movimiento está asociado a otro recibo.

## Devoluciones (R19/C19)

### POST `/api/v1/devoluciones/import`
Importar fichero de devoluciones del banco (R19/C19) o notificaciones individuales.
- Multipart `file` (texto plano AEB) con query `tipo=R19|C19` (por defecto `R19`) o Body: `{ "devoluciones": [ { "recibo_id", "tipo": "R19" | "C19", "codigo", "motivo", "importe", "fecha_registro", "importe_gastos"? } ] }`. Ambos tipos usan el registro AEB tipo 3 y conservan el tipo en el identificador de idempotencia.
- Reglas: para cada devolución genera `DevolucionRecibo` + asiento `REVERSAL` (572/570 contra deuda, gastos en 626), reabre el vencimiento y marca el recibo `devuelto`; el identificador externo del retorno evita reprocesados.
- 200: `{ "procesadas": n, "rechazadas": [ { "motivo", "code" } ] }`
- 409: devolución de un recibo no cobrado o de ejercicio cerrado.

### POST `/api/v1/devoluciones/{id}/reclamaciones`
Crear/avanzar reclamación de una devolución.
- Body: `{ "accion": "abrir" | "en_curso" | "resolver" | "desestimar", "observaciones"? }`
- 200: `{ "reclamacion_id", "estado" }`

## Descuento por pronto pago

### POST `/api/v1/recibos/{recibo_id}/liquidar`
Liquidar un vencimiento aplicando pronto pago si procede.
- Body: `{ "fecha_pago": "YYYY-MM-DD", "cuenta": "5720000", "override_condicion_id"? }`
- Reglas: aplica `CondicionProntoPago` vigente del tercero (o el override por factura); si `fecha_pago - fecha_factura <= plazo_dias` aplica el %, neto>=0. Asiento: Debe 572 (neto) + 432/662 (descuento); Haber 430 (total).
- 200: `{ "importe_neto", "descuento", "asiento_id" }`

## Maestro (ampliación SPEC-008)

### POST/PATCH `/api/v1/terceros/{id}/condiciones` · `/mandatos`
CRUD de `CondicionProntoPago` y `MandatoSepa` (ver [data-model](../data-model.md)).

## Tratamiento de errores

- `401/403`: autenticación/permisos (SPEC-003).
- `404`: recurso inexistente en la empresa activa (nunca filtra datos de otra empresa).
- `409`: conflicto de estado (ejercicio cerrado, recibo ya cobrado, remesa ya emitida).
- `422`: validación de negocio (importes, plazos SEPA, IBAN, mandatos, correlatividad).
- Errores de importes siempre en precisión decimal; el backend es el único que valida partida doble.