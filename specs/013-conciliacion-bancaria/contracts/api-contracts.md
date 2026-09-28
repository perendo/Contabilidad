# API Contracts: Conciliación Bancaria (SPEC-013)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Estilo: REST bajo `/api/v1/...` (los endpoints exigen la cabecera de sesión autenticada; el **`empresa_id` activo se deriva EXCLUSIVAMENTE de la cabecera de sesión** — nunca viaja en path ni en body). Respuestas JSON; importes como strings decimales (p. ej. `"123.4500"`), nunca números de coma flotante. Todos los endpoints verifican la empresa activa: un recurso de otra empresa → `404`.

## Extractos

### POST `/api/v1/extractos`
Importar un fichero de extracto (norma 43/19 o CSV normalizado) para una cuenta 572.
- `multipart/form-data`: `file` (fichero), campos opcionales `layout` (`norma_43_1919` | `csv_normalizado`) y `concepto_norma` (normalización).
- Reglas: valida la cuenta 572 del plan de la empresa activa; calcula `sha256`; detecta duplicados (huella y solapamiento por rango/saldos/nº movimientos); persiste extracto + movimientos + auditoría en una transacción ACID.
- 201: `{ "id", "cuenta_id", "fecha_inicio", "fecha_fin", "saldo_inicial", "saldo_final", "n_movimientos", "estado": "importado" }`
- 409: extracto duplicado `{ "error": "extracto_duplicado", "extracto_existente_id" }`
- 422: fichero malformado `{ "error": "layout_invalido", "registro": n, "campo": "..." }`
- 404: cuenta 572 inexistente en la empresa activa.

### GET `/api/v1/extractos`
Listado con filtros `cuenta_id`, `fecha_fin[gte/lte]`, `estado`, paginación.
- 200: `{ "items": [{ "id", "cuenta_id", "fecha_inicio", "fecha_fin", "saldo_final", "estado", "n_movimientos", "sha256" }], "total" }`

### GET `/api/v1/extractos/{id}`
Detalle del extracto con sus movimientos (paginado).
- 200: `{ ...extracto, "movimientos": [{ "id", "orden", "fecha_operacion", "concepto", "importe", "signo", "estado" }] }`
- 404 si no pertenece a la empresa activa.

## Conciliación

### POST `/api/v1/conciliaciones`
Abrir una conciliación para una cuenta 572 en un rango de fechas.
- Body: `{ "cuenta_id", "fecha_inicio": "YYYY-MM-DD", "fecha_fin": "YYYY-MM-DD", "extracto_id" }` (extracto_id opcional; si se omite se usa el último extracto del rango).
- Reglas: una sola conciliación abierta por (cuenta, rango solapado); ejercicio abierto (SPEC-004); calcula saldos iniciales.
- 201: `{ "id", "cuenta_id", "saldo_banco", "saldo_libros", "diferencia", "estado": "abierta" }`
- 409: ejercicio cerrado, o conciliación previa abierta en el rango.

### GET `/api/v1/conciliaciones`
Listado con filtros `cuenta_id`, `estado`, `ejercicio`, paginación.

### GET `/api/v1/conciliaciones/{id}`
Informe de conciliación (estado al momento):
- 200: `{ "id", "cuenta_id", "saldo_banco", "saldo_libros", "diferencia", "pendientes": { "movimientos_sin_cruzar": [...], "apuntes_sin_extracto": [...] }, "alertas": [...], "saldos": "NUMERIC(18,4)" }`
- 404 si no pertenece a la empresa activa.

### POST `/api/v1/conciliaciones/{id}/propuestas`
Generar (o regenerar) propuestas automáticas de cruce.
- Body: `{ "ir_remesa": true }` (parámetros opcionales de priorización; por defecto regenera solo cruces no confirmados).
- Reglas: cruza por importe exacto + orientación; prioriza por concepto normalizado; no crea cruces duplicados; respeta los ya confirmados.
- 200: `{ "propuestas": [{ "id", "movimiento_id", "apunte_id", "importe", "signo", "prioridad": "propuesto"|"candidato" }], "n_propuestas" }`

### POST `/api/v1/conciliaciones/{id}/cruces`
Confirmar propuesta/s o reclamar cruce manual.
- Body: `{ "cruces": [ { "movimiento_id", "apunte_id", "origen": "auto"|"manual" } ] }`
- Reglas: valida importe exacto entre movimiento y apunte (`Decimal`); un movimiento/apunte solo conciliado una vez; si el apunte corresponde a un cobro de remesa (SPEC-020), confirma el cobro del recibo en la misma transacción ACID.
- 201: `{ "confirmados": [{ "cruce_id", "movimiento_id", "apunte_id", "fecha_cruce", "confirmado_por_remesa" }], "rechazados": [{ "motivo" }] }`
- 409: cruce de un movimiento/apunte ya conciliado; período de ejercicio cerrado; diferencia que deja saldo fuera de cuádruple consistencia (no procede: el saldo se recalcula siempre).

### DELETE `/api/v1/conciliaciones/{id}/cruces/{cruce_id}`
Deshacer un cruce (solo antes de archivar el período).
- 204 si el cruce existía en la empresa activa; 409 si el período ya está archivado (inmutable, constitución II).

## Cierre y períodos

### POST `/api/v1/conciliaciones/{id}/cerrar`
Cerrar la conciliación: archiva el período con diferencia cero.
- Reglas: `diferencia == Decimal("0.0000")`; asigna `numero_periodo` correlativo por (empresa, ejercicio) atómicamente; audita; período inmutable.
- 200: `{ "periodo_id", "numero_periodo", "fecha_inicio", "fecha_fin", "saldo_banco", "saldo_libros", "diferencia": "0.0000" }`
- 409: diferencia != 0 `{ "error": "diferencia_no_cero", "diferencia", "pendientes": [...] }` — no archiva, advierte.

### GET `/api/v1/periodos-conciliados`
Períodos archivados de la empresa activa (filtro `ejercicio`, `cuenta_id`, paginación).
- 200: `{ "items": [{ "id", "numero_periodo", "ejercicio", "cuenta_id", "fecha_inicio", "fecha_fin", "saldo_banco", "saldo_libros" }], "total" }`

## Alertas

### POST `/api/v1/conciliaciones/{id}/alertas/{alerta_id}/resolver`
Resolver una alerta de operación sin correspondencia (informativa; nunca crea asiento).
- Body: `{ "observaciones"? }`
- 200: `{ "alerta_id", "estado": "resuelta" }`

## Tratamiento de errores

- `401/403`: autenticación/permisos (SPEC-003; para permisos por operación ver SPEC-015).
- `404`: recurso inexistente en la empresa activa (nunca filtra datos de otra empresa).
- `409`: conflicto de estado (extracto duplicado, ejercicio cerrado, cruce ya existente, cierre con diferencia != 0).
- `422`: validación de negocio (layout del fichero, importes, fechas, cuenta no 572).
- Importes siempre en precisión decimal; la conciliación nunca modifica asientos `POSTED`.
- Acoplamiento SPEC-020: al confirmar un cruce de un cobro de remesa, el recibo pasa a `cobrado` (ver `../quickstart.md` Scenario 4 y [data-model](../data-model.md)).