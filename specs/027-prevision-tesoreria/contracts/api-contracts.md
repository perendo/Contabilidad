# API Contracts: Previsión y Flujo de Caja (SPEC-027)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Estilo: REST bajo `/api/v1/...`. El `empresa_id` (a.k.a. `tenant_id`) activo se deriva **exclusivamente de la cabecera de sesión autenticada** — nunca del path ni del body (constitución III). Respuestas JSON; importes como strings decimales (p. ej. `"1250.0000"`), nunca coma flotante.

## Previsión de tesorería

### GET `/api/v1/tesoreria/previsiones`
Listado de previsiones con filtros `estado`, `granularidad`, `desde_fecha[gte]`, paginación.
- 200: `{ "items": [{ "id", "numero_prevision", "fecha_generacion", "desde_fecha", "hasta_fecha", "granularidad", "saldo_inicial", "saldo_final", "estado" }], "total" }`

### POST `/api/v1/tesoreria/previsiones`
Generar una previsión desde vencimientos pendientes (SPEC-011/020) + movimientos manuales.
- Body: `{ "desde_fecha": "2026-09-16", "hasta_fecha": "2026-12-31", "granularidad": "dia" | "semana" | "mes", "movimientos_manuales": [ { "tipo": "cobro" | "pago", "importe": "500.0000", "fecha_prevista": "2026-09-30", "frecuencia": "unico" | "semanal" | "mensual" | "anual", "concepto": "Alquiler" } ] }`
- Reglas: vencimientos pendientes con fecha prevista entran; vencidos/cobrados/pagados o sin fecha se excluyen (FR-006 y se reportan como `excluidos`); `numero_prevision` correlativo por empresa.
- 201: `{ "id", "numero_prevision", "granularidad", "saldo_inicial", "saldo_final", "n_movimientos", "excluidos": [{ "origen", "motivo": "vencido" | "cobrado" | "sin_fecha" }] }`
- 422: fechas inválidas, importes no decimales o negativos.

### GET `/api/v1/tesoreria/previsiones/{id}`
Detalle de la previsión con sus buckets (fecha, movimientos, saldo acumulado).
- 200: `{ "id", "numero_prevision", "granularidad", "saldo_inicial", "saldo_final", "buckets": [{ "fecha", "cobros": "x.0000", "pagos": "y.0000", "saldo_acumulado": "z.0000", "alerta": false }] }`
- 404: previsión inexistente en la empresa activa.

## Alertas de liquidez

### GET `/api/v1/tesoreria/alertas?prevision_id=&estado=`
Listado de alertas de la empresa activa (días/meses con saldo proyectado negativo).
- 200: `{ "items": [{ "id", "fecha", "saldo_proyectado", "importe_deficit", "estado", "accion_sugerida", "movimiento_origen_id" }] }`

### POST `/api/v1/tesoreria/alertas/{id}/atender`
Aplicar la acción sugerida: reprogramar pago o incluir ingreso previsto.
- Body: `{ "accion": "reprogramar_pago" | "incluir_ingreso", "movimiento_id": "<uuid|null>", "nueva_fecha": "2026-10-15", "importe": "3000.0000" }`
- Reglas: `reprogramar_pago` actualiza `MovimientoPrevision.fecha_prevista`; `incluir_ingreso` crea un `MovimientoPrevision` de cobro; la alerta pasa a `atendida`; audit log.
- 200: `{ "alerta_id", "estado": "atendida", "movimiento_id" }`
- 409: alerta ya atendida/ignorada.

### POST `/api/v1/tesoreria/alertas/{id}/ignorar`
Desestimar la alerta (trazable). 200: `{ "alerta_id", "estado": "ignorada" }`.

## Informe EFE

### GET `/api/v1/tesoreria/efe?ejercicio=`
Informe de Flujo de Efectivo del ejercicio de la empresa activa.
- 200: `{ "ejercicio", "saldo_inicial", "saldo_final", "cuadre": true, "sin_conciliar": false, "bloques": { "operativa": { "total": "x.0000", "items": [ { "cuenta_id", "codigo_cuenta", "importe" } ] }, "inversion": {...}, "financiacion": {...} } }`
- Verifica `saldo_inicial + Σ bloques == saldo_final` (FR-004).

### POST `/api/v1/tesoreria/efe/formular`
Formular el EFE del ejercicio: fija el snapshot inmutable (`estado = formulado`).
- Body: `{ "ejercicio": 2026, "clasificaciones": [ { "cuenta_id", "bloque": "operativa" | "inversion" | "financiacion" } ] }`
- Reglas: los overrides de clasificación se permiten antes de formular; cuadre obligatorio (422 si no cuadra); cruce con SPEC-013 advierte (`sin_conciliar`) pero no bloquea.
- 200: `{ "informe_id", "estado": "formulado", "cuadre": true, "sin_conciliar": false }`
- 409: ejercicio ya formulado o ejercicio cerrado; 422: cuadre fallido.

## Tratamiento de errores

- `401/403`: autenticación/permisos (SPEC-003); `403` si la empresa del contexto no pertenece al usuario.
- `404`: recurso inexistente en la empresa activa (nunca filtra datos de otra empresa).
- `409`: conflicto de estado (alerta atendida/ignorada, EFE ya formulado, ejercicio cerrado).
- `422`: validación de negocio (fechas, importes, movimientos sin fecha prevista, cuadre EFE fallido).
- El backend es la única fuente de verdad de los saldos proyectados (precisiones decimales); la UI es informativa.