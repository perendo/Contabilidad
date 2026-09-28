# API Contracts: Libros de IVA y Modelos Fiscales (SPEC-012)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Estilo: REST bajo `/api/v1/...` (empresa activa derivada de sesion en cabecera; `empresa_id` nunca en body/path como dato de seleccion). Respuestas JSON; importes como strings decimales (p. ej. `"1234.5000"`), nunca numeros de coma flotante. Los ficheros de exportacion se descargan como adjuntos.

## Libros de IVA

### GET `/api/v1/libros-iva/{tipo_libro}`
Obtener el libro de IVA del periodo: tipo_libro = `emitidas|recibidas|intracomunitarias`.
- Query params: `ejercicio`, `periodo` (trimestre 1-4 o mes 1-12), `tipo_periodo` (`TRIMESTRE|MES`), `fecha_desde`, `fecha_hasta`, `clave_operacion` (opcional), `tercero_id` (opcional).
- 200: `{ "ejercicio", "tipo_libro", "periodo", "operaciones": [{ "factura_id", "nif_tercero", "fecha_expedicion", "num_factura", "base", "cuota", "tipo_iva", "recargo_cuota", "incluir_303" }], "total_base", "total_cuota", "total_recargo" }`
- 409: `ejercicio_no_definido`, `periodo_fuera_de_rango`.

## Modelos Fiscales

### GET `/api/v1/modelos/303`
Calcular el modelo 303 del periodo (cuadrado con libros).
- Query params: `ejercicio`, `periodo`, `tipo_periodo`.
- 200: `{ "ejercicio", "periodo", "devengado": { "base": {...}, "cuota": {...} }, "deducible": { "base": {...}, "cuota": {...} }, "recargo_equivalencia": { "cuota": "0.0000" }, "resultado": { "a_ingresar": "0.0000", "a_compensar": "0.0000" }, "cuadre_libros": true, "iva_diferido": { "pendiente": "0.0000" } }`
- 422: `descuadre_libros` (bases/cuotas difieren de los libros del periodo).
- 409: si el periodo no tiene definidos sus libros o el ejercicio no existe.

### GET `/api/v1/modelos/347`
Preparar el resumen anual de operaciones con terceros.
- Query params: `ejercicio`, `limite_incluir` (default 3005.06).
- 200: `{ "ejercicio", "operaciones": [{ "nif_tercero", "nombre", "clave_operacion", "importe_acumulado", "n_operaciones" }], "total_general" }`

### GET `/api/v1/modelos/349`
Preparar el modelo de operaciones intracomunitarias del periodo.
- Query params: `ejercicio`, `periodo`, `tipo_periodo`.
- 200: `{ "ejercicio", "periodo", "operaciones": [{ "nif_tercero", "clave_operacion", "tipo_operacion", "importe" }], "total_general" }`

## Exportacion de Modelos

### POST `/api/v1/exportaciones`
Generar y registrar la exportacion de un modelo (303/347/349) como fichero.
- Body: `{ "modelo": "303|347|349", "ejercicio", "periodo"?, "tipo_periodo"?, "formato": "csv|xml|json" }`
- Reglas: ejecuta el calculo con cuadre previo; genera fichero; numero_exportacion correlativo por (empresa, ejercicio, modelo); persiste hash. Si el periodo ya fue exportado y se regenera, advertencia `re-exportado` incluida en la respuesta.
- 201: `{ "exportacion_id", "numero_exportacion", "modelo", "periodo", "fichero": { "nombre", "sha256", "url_descarga" }, "advertencia": null }`
- 422: `descuadre_libros`, `calculo_no_cuadra`.
- 409: `ejercicio_cerrado`, `modelo_no_preparado`.

### GET `/api/v1/exportaciones/{id}/descargar`
Descargar el fichero de la exportacion.
- 200: adjunto con content-type por formato (`text/csv`, `application/xml`, `application/json`).
- 404: si la exportacion no pertenece a la empresa activa.

### GET `/api/v1/exportaciones`
Historico de exportaciones con filtros `modelo`, `ejercicio`, `periodo`, `estado`.
- 200: `{ "items": [{ "exportacion_id", "numero_exportacion", "modelo", "periodo", "fecha", "usuario", "sha256", "estado" }], "total" }`

## Regimenes Especiales

### GET `/api/v1/regimenes/estado`
Estado de regimenes de la empresa activa (configuracion de cuentas de IVA/recargo y de criterio de caja).
- 200: `{ "recargo_equivalencia": { "habilitado": false, "cuenta_recargo": "4770000" }, "criterio_caja": { "habilitado": false, "diferidos_pendientes": "0.0000" }, "sii": { "habilitado": false, "obligatorio": false } }`

### POST `/api/v1/regimenes/recargo-equivalencia`
Habilitar/configurar el recargo de equivalencia (cuenta de recargo separada).
- Body: `{ "habilitado": true, "cuenta_recargo": "4771000" }`
- 200: `{ "habilitado": true, "cuenta_recargo" }`

### POST `/api/v1/regimenes/criterio-caja`
Habilitar/configurar el criterio de caja (el IVA diferido depende de los vencimientos de SPEC-011).
- Body: `{ "habilitado": true }`
- 200: `{ "habilitado": true, "diferidos_pendientes" }`

## Configuracion SII (interfaz, sin envio)

### GET `/api/v1/sii/configuracion`
Obtener la configuracion SII de la empresa activa.
- 200: `{ "habilitado": false, "obligatorio": false, "identificador_emisor": "B12345678", "periodicidad_303": "TRIMESTRE" }`

### POST `/api/v1/sii/configuracion`
Habilitar/actualizar el enlace SII (interfaz declarada; la presentacion ejecutada la cubre SPEC-029).
- Body: `{ "habilitado": true, "identificador_emisor": "B12345678" }`
- Reglas: si habilitado, exige periodicidad 303 `MES` (ajusta automaticamente con advertencia).
- 200: `{ "habilitado": true, "periodicidad_303": "MES", "advertencia": "periodicidad_ajustada_a_mensual" }`

### GET `/api/v1/sii/operaciones/{tipo}`
Generar el XML SII pendiente de envio de un periodo (emitidas/recibidas) — NO envia. El envio se integra con SPEC-029.
- Query params: `ejercicio`, `periodo`, `tipo_periodo`.
- 200: `{ "xml", "sha256", "n_operaciones" }` (sin registro de envio).

## Tratamiento de errores

- `401/403`: autenticacion/permisos (SPEC-003).
- `404`: recurso inexistente en la empresa activa.
- `409`: conflicto de estado (ejercicio cerrado, periodo no definido, modelo no preparado).
- `422`: validacion de negocio (descuadre con libros, calculo no cuadra, limite 347).
- Los cuadres se verifican siempre en backend; el frontend solo muestra estados.