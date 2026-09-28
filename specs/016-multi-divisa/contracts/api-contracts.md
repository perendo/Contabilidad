# API Contracts: Multi-Divisa (SPEC-016)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Estilo: REST bajo `/api/v1/...` (los endpoints exigen la cabecera de sesión autenticada; el **`empresa_id` activo se deriva EXCLUSIVAMENTE de la cabecera de sesión** — nunca viaja en path ni en body). Respuestas JSON; importes y ratios como strings decimales (`"1500.0000"`; tipos `"1.08500000"`), nunca coma flotante. Un recurso de otra empresa → `404`. No aplican formatos de fichero externos.

## Monedas

### GET `/api/v1/divisas`
Divisas de la empresa activa.
- 200: `{ "funcional": "EUR", "items": [{ "id", "codigo_iso", "activa" }] }`

### POST `/api/v1/divisas`
Registrar una divisa de trabajo.
- Body: `{ "codigo_iso": "USD", "activa": true }`
- 201: `{ "id", "codigo_iso", "es_funcional": false, "activa": true }`
- 409: divisa ya registrada; 422: código ISO inválido o intento de segunda funcional.

## Tipos de cambio

### POST `/api/v1/tipos-cambio`
Registrar/actualizar un tipo no sellado para una divisa y fecha.
- Body: `{ "divisa_id", "fecha": "2026-10-01", "ratio": "1.08500000" }`
- 201: `{ "id", "divisa_id", "fecha", "ratio", "sellado": false }`
- 409: tipo sellado (inmutable, FR-006); tipo existente para (divisa, fecha) → 409 (usar PATCH si está sin sellar).

### PATCH `/api/v1/tipos-cambio/{id}`
Corregir un tipo sin sellar (con trazabilidad).
- Body: `{ "ratio": "1.09000000", "motivo": "corrección entrada" }`
- 200: `{ "id", "ratio", "sellado": false, "auditado": true }`
- 409: tipo sellado → prohibido modificar (constitución II).

### GET `/api/v1/tipos-cambio`
Histórico por divisa/fecha (filtro `divisa_id`, `fecha[gte/lte]`, `sellado`, paginación).
- 200: `{ "items": [{ "id", "divisa_id", "fecha", "ratio", "sellado", "usos_posteados" }], "total" }`

### GET `/api/v1/tipos-cambio/historial`
Histórico aplicado a los asientos: por cada asiento en divisa el tipo exacto usado (fecha y ratio).
- Query: `asiento_id` o rango de fechas.
- 200: `{ "items": [{ "asiento_id", "fecha", "ratio", "sellado": true }] }` — reproduce asientos (FR-003/SC-002).

## Asientos en divisa

### POST `/api/v1/asientos-divisa`
Registrar un asiento en divisa (ampliación de SPEC-002).
- Body: `{ "fecha": "2026-10-01", "divisa_id", "lineas": [{ "cuenta_id", "debe_divisa": "1000.0000", "haber_divisa": "0.0000" }], "tipo_cambio_id"?, "tipo_ratio_explicito": { "ratio", "fecha_valor" }? }`
- Reglas: valida el tipo de la fecha (o persiste el tipo explícito en la misma transacción); convierte cada línea con `Decimal` y `ROUND_HALF_EVEN`; imputa el remanente a línea de redondeo (658/668 ó 769) si existe; **cuadra en divisa y en funcional** (Debe==Haber en ambas); numera y postea via motor SPEC-002; sella el tipo en la misma transacción; audita.
- 201: `{ "asiento_id", "numero_asiento", "divisa_id", "tipo_cambio_id", "ratio", "importe_total_divisa", "importe_total_funcional", "linea_redondeo": { "cuenta", "importe" } }`
- 422: sin tipo para la fecha y sin tipo explícito; desequilibrio no imputable; divisa no activa; 409: ejercicio cerrado.

### GET `/api/v1/asientos-divisa/{asiento_id}`
Detalle del asiento en divisa con líneas en divisa y funcional.
- 200: `{ "asiento_id", "fecha", "divisa_id", "tipo_cambio_id", "ratio", "lineas": [{ "linea_id", "cuenta_id", "debe_divisa", "haber_divisa", "debe_funcional", "haber_funcional", "es_linea_redondeo" }], "total_divisa", "total_funcional" }`
- 404 si no pertenece a la empresa activa o no es en divisa.

## Valoración a cierre

### POST `/api/v1/valoraciones`
Valorar los saldos en divisa a una fecha de cierre y generar asientos de diferencias de cambio.
- Body: `{ "ejercicio": 2026, "fecha_valoracion": "2026-12-31" }`
- Reglas: iterar saldos vivos por cuenta en divisa; usar el tipo de cierre de la fecha (asegurar existencia o 422); calcular `diferencia = saldo_divisa × tipo_cierre − saldo_funcional_previo` con `Decimal`; generar asiento balanceado (Debe 668 pérdida / Haber 769 ganancia) vinculado al cierre; no duplicar valoraciones ya asentadas.
- 200: `{ "valoraciones": [{ "id", "cuenta_id", "divisa_id", "saldo_divisa", "diferencia", "asiento_id" }], "n": k }`
- 409: ejercicio cerrado; valoración duplicada; 422: sin tipo de cierre.

### GET `/api/v1/diferencias-cambio`
Listado de diferencias de cambio generadas (filtro `ejercicio`, `divisa_id`, `cuenta_id`, paginación).
- 200: `{ "items": [{ "id", "ejercicio", "fecha_valoracion", "cuenta_id", "divisa_id", "diferencia", "asiento_id", "estado" }], "total" }`

## Tratamiento de errores

- `401/403`: autenticación/permisos (SPEC-003; permisos por operación ver SPEC-015).
- `404`: recurso inexistente en la empresa activa (nunca filtra datos de otra empresa).
- `409`: conflicto de estado (tipo sellado, ejercicio cerrado, valoración duplicada, divisa duplicada).
- `422`: validación de negocio (falta de tipo, desequilibrio doble moneda, ratio inválido, divisa no activa).
- Importes siempre en precisión decimal; el backend valida el cuadre en divisa y en funcional (constitución I); nunca se modifica un asiento `POSTED` ni un tipo sellado.