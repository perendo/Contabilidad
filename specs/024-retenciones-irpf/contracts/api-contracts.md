# API Contracts: Retenciones IRPF y Modelos 111/115/190 (SPEC-024)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Estilo: REST bajo `/api/v1` (todos los endpoints exigen la cabecera de empresa activa derivada de sesión; la empresa activa se deriva exclusivamente de la sesión, nunca del path). Respuestas JSON; importes como strings decimales.

## Liquidación de Retenciones

### POST `/api/v1/fiscal/retenciones/liquidaciones`
Crear una liquidación trimestral de retenciones (acumula retenciones del trimestre).
- Body: `{ "ejercicio": 2025, "trimestre": 3 }`
- Reglas: acumula retenciones de facturas (SPEC-007) del trimestre natural; calcula total_base_retenciones y total_retenciones; valida que no exista liquidación previa para ese trimestre.
- 201: `{ "id", "periodo": "2025-Q3", "total_base_retenciones", "total_retenciones", "n_perceptores", "estado": "pendiente" }`
- 409: liquidación ya existente para ese trimestre.

### GET `/api/v1/fiscal/retenciones/liquidaciones`
Listado de liquidaciones con filtros: `ejercicio`, `trimestre`, `estado`, paginación.
- 200: `{ "items": [{ "id", "ejercicio", "trimestre", "total_retenciones", "estado", "fecha_liquidacion" }], "total" }`

### GET `/api/v1/fiscal/retenciones/liquidaciones/{id}`
Detalle de liquidación con retenciones por perceptor.
- 404 si no pertenece a la empresa activa.

### POST `/api/v1/fiscal/retenciones/liquidaciones/{id}/contabilizar`
Generar el asiento de liquidación (4751 vs 572) de forma balanceada y atómica.
- Body: `{ "fecha_asiento": "YYYY-MM-DD", "cuenta_banco": "5720000" }`
- Reglas: liquidación en estado `pendiente`; generar asiento Debe 4751 (total_retenciones) | Haber 572 (total_retenciones); cambiar estado a `liquidado`.
- 200: `{ "asiento_id", "estado": "liquidado" }`
- 409: liquidación ya contabilizada.
- 422: total_retenciones = 0.

## Retenciones por Periodo

### GET `/api/v1/fiscal/retenciones/liquidaciones/{id}/retenciones`
Detalle de retenciones de una liquidación agrupadas por perceptor.
- 200: lista de `RetencionPeriodo` con tercero, NIF, nombre, tipo, base, tipo_porcentaje, retencion_practicada, facturas.

## Modelos 111 y 115

### POST `/api/v1/fiscal/retenciones/modelos-111`
Generar el modelo 111 a partir de una liquidación.
- Body: `{ "liquidacion_id": "<uuid>" }`
- Reglas: liquidación en estado `pendiente` o `liquidado`; genera contenido JSONB con bloques del modelo 111.
- 201: `{ "id", "hash_contenido", "fecha_generacion" }`
- 409: modelo ya generado para esa liquidación.

### GET `/api/v1/fiscal/retenciones/modelos-111/{id}`
Descargar el modelo 111 (PDF/CSV).
- 200: fichero descargable.
- 404 si no pertenece a la empresa activa.

### POST `/api/v1/fiscal/retenciones/modelos-115`
Generar el modelo 115 (arrendamientos) a partir de una liquidación que contenga retenciones de arrendamiento.
- Body: `{ "liquidacion_id": "<uuid>" }`
- Reglas: solo si hay retenciones de tipo `IRPF_ARRENDAMIENTOS`.
- 201: `{ "id", "hash_contenido" }`
- 409: modelo ya generado, sin retenciones de arrendamiento.

### GET `/api/v1/fiscal/retenciones/modelos-115/{id}`
Descargar el modelo 115.

## Modelo 190 Anual

### POST `/api/v1/fiscal/retenciones/modelo-190`
Generar el modelo 190 anual con resumen por perceptor.
- Body: `{ "ejercicio": 2025 }`
- Reglas: agrupa retenciones de todos los trimestres del año por perceptor; exige NIF en todos los perceptores; valida que la suma anual coincida con las trimestrales.
- 201: `{ "id", "hash_contenido", "n_perceptores", "fecha_generacion" }`
- 409: modelo ya generado para ese ejercicio.
- 422: perceptores sin NIF (lista de los que faltan).

### GET `/api/v1/fiscal/retenciones/modelo-190/{id}`
Descargar el modelo 190 (PDF/CSV).
- 200: fichero descargable.
- 404 si no pertenece a la empresa activa.

### GET `/api/v1/fiscal/retenciones/modelo-190/validar`
Validar antes de generar: verificar que todos los perceptores del año tienen NIF.
- Body query: `ejercicio=2025`
- 200: `{ "valido": true }` o `{ "valido": false, "perceptores_sin_nif": [{ "tercero_id", "nombre" }] }`

## Tratamiento de errores

- `401/403`: autenticación/permisos (SPEC-003).
- `404`: recurso inexistente en la empresa activa.
- `409`: conflicto (liquidación ya existente, modelo ya generado).
- `422`: validación de negocio (trimestre inválido, sin retenciones, perceptores sin NIF).
- Errores de importes siempre en precisión decimal; el backend es el único que valida partida doble.
