# API Contracts: Impuesto sobre Sociedades (Modelo 200) (SPEC-023)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Estilo: REST bajo `/api/v1` (todos los endpoints exigen la cabecera de empresa activa derivada de sesión; la empresa activa se deriva exclusivamente de la sesión, nunca del path). Respuestas JSON; importes como strings decimales.

## Cálculo del IS

### POST `/api/v1/fiscal/is/calculos`
Crear un cálculo del IS para un ejercicio.
- Body: `{ "ejercicio": 2025, "provisional": false }`
- Reglas: el resultado contable se obtiene automáticamente del cierre (SPEC-004); el tipo impositivo se toma de la configuración fiscal de la empresa; pagos a cuenta se calculan del submayor 473.
- 201: `{ "id", "ejercicio", "resultado_contable", "tipo_impositivo", "cuota_integra", "pagos_a_cuenta", "cuota_diferencial", "provisional" }`
- 409: ya existe un cálculo definitivo para ese ejercicio.
- 422: ejercicio no cerrado (para cálculo definitivo), sin datos de cierre.

### GET `/api/v1/fiscal/is/calculos`
Listado de cálculos del IS con filtros: `ejercicio`, `provisional`, `estado`, paginación.
- 200: `{ "items": [{ "id", "ejercicio", "base_imponible", "cuota_integra", "cuota_diferencial", "provisional", "estado" }], "total" }`

### GET `/api/v1/fiscal/is/calculos/{id}`
Detalle del cálculo con todos los campos y ajustes asociados.
- 404 si no pertenece a la empresa activa.

### POST `/api/v1/fiscal/is/calculos/{id}/recalcular`
Recalcular un cálculo (provisional o definitivo) con ajustes actualizados.
- Body: `{ "ajustes": [{ "tipo": "AJUSTE_POSITIVO", "descripcion": "...", "importe": "5000.0000" }], "deducciones": [{ "tipo": "DEDUCCION", "descripcion": "...", "importe": "3000.0000" }] }`
- Reglas: recalcula base, cuota y diferencial; mantiene el estado `calculado`.
- 200: `{ "base_imponible", "cuota_integra", "cuota_liquida", "cuota_diferencial" }`
- 409: cálculo ya contabilizado.

### POST `/api/v1/fiscal/is/calculos/{id}/contabilizar`
Generar el asiento del IS (630 vs 473/4752/4757) de forma balanceada y atómica.
- Body: `{ "fecha_asiento": "YYYY-MM-DD" }`
- Reglas: cálculo en estado `calculado`; generar asiento Debe 630 (cuota_liquida) | Haber 473 (pagos_a_cuenta) + 4752/4757 (cuota_diferencial si es a pagar) o Debe 630 + 4709 (si es a devolver) | Haber 473. Cambiar estado a `contabilizado`.
- 200: `{ "asiento_id", "estado": "contabilizado" }`
- 409: cálculo no está en estado `calculado`.

## Ajustes Extracontables

### POST `/api/v1/fiscal/is/calculos/{id}/ajustes`
Registrar un ajuste o deducción en un cálculo.
- Body: `{ "tipo": "AJUSTE_POSITIVO|AJUSTE_NEGATIVO|DEDUCCION|BONIFICACION", "descripcion": "string", "referencia_normativa"?: "string", "importe": "5000.0000" }`
- 201: `{ "id", "tipo", "importe" }`
- 409: cálculo ya contabilizado.
- 422: importe <= 0.

### GET `/api/v1/fiscal/is/calculos/{id}/ajustes`
Listado de ajustes de un cálculo.
- 200: lista de ajustes con tipo, descripción e importe.

### DELETE `/api/v1/fiscal/is/calculos/{id}/ajustes/{ajuste_id}`
Eliminar un ajuste (solo si el cálculo no está contabilizado).
- 200: ok.
- 409: cálculo ya contabilizado.

## Modelo 200

### POST `/api/v1/fiscal/is/modelo-200`
Generar el modelo 200 a partir de un cálculo contabilizado.
- Body: `{ "calculo_is_id": "<uuid>" }`
- Reglas: el cálculo debe estar contabilizado; valida consistencia entre bloques.
- 201: `{ "id", "hash_contenido", "fecha_generacion" }`
- 409: cálculo no contabilizado, modelo ya generado.
- 422: inconsistencia en los datos del cálculo.

### GET `/api/v1/fiscal/is/modelo-200/{id}`
Descargar el modelo 200 (PDF/CSV).
- 200: fichero descargable con `Content-Disposition`.
- 404 si no pertenece a la empresa activa.

## Configuración Fiscal

### GET/PATCH `/api/v1/fiscal/configuracion`
Consultar/actualizar la configuración fiscal de la empresa (tipo impositivo IS, vigencia).
- GET: `{ "tipo_is": "25.00", "fecha_vigencia_desde": "2025-01-01" }`
- PATCH Body: `{ "tipo_is": "25.00", "fecha_vigencia_desde": "2025-01-01" }`

## Tratamiento de errores

- `401/403`: autenticación/permisos (SPEC-003).
- `404`: recurso inexistente en la empresa activa.
- `409`: conflicto (cálculo ya definitivo, ya contabilizado, ejercicio no cerrado para definitivo).
- `422`: validación de negocio (campos, consistencia de cálculo, importes).
- Errores de importes siempre en precisión decimal; el backend es el único que valida partida doble.
