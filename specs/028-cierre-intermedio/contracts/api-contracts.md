# API Contracts: Cierre Intermedio y Reapertura Controlada (SPEC-028)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Estilo: REST bajo `/api/v1/cierres`. **El `empresa_id` activo se deriva exclusivamente de la cabecera de sesión `X-Empresa-Id` (o token de sesión): nunca viaja en el path ni en el body de la petición.** Respuestas JSON; importes como `Decimal` strings (p. ej. `"123.4500"`), nunca números de coma flotante. El backend es el único validador de partida doble; la UI es informativa.

## Cierres intermedios (mes/trimestre)

### POST `/api/v1/cierres/intermedios`
Cerrar un periodo intermedio de la empresa activa: valida el rango, calcula el balance de comprobación del periodo (snapshot) y bloquea la contabilización en esas fechas. No crea ni modifica asientos del diario.
- Body: `{ "ejercicio": 2026, "tipo": "MES" | "TRIMESTRE", "periodo": 3 }`
- Reglas: la fecha de los asientos del periodo cae dentro de `fecha_ini..fecha_fin` derivado del calendario; al persistir, `total_debe == total_haber` (si no cuadra, 409 sin cerrar).
- 201: `{ "periodo_id", "ejercicio", "tipo", "periodo", "estado": "cerrado", "balanza": { "id", "total_debe", "total_haber", "cuadra": true, "n_lineas" }, "resultado_provisional" }`
- 404: ejercicio inexistente en la empresa activa.
- 409: periodo ya cerrado | periodo cubierto por un trimestre cerrado | ejercicio de la empresa activa ya cerrado (`is_closed`) | periodos anteriores sin cerrar si la configuración lo exige.
- 422: `tipo`/`periodo` fuera de rango, ejercicio no numérico, `periodo` no aplica al `tipo`.

### GET `/api/v1/cierres/intermedios`
Listado de periodos intermedios con filtros `ejercicio`, `tipo`, `estado`, paginación.
- 200: `{ "items": [ { "periodo_id", "ejercicio", "tipo", "periodo", "fecha_ini", "fecha_fin", "estado", "n_reaperturas" } ], "total" }`

### GET `/api/v1/cierres/intermedios/{periodo_id}/balanza`
Balance de comprobación del periodo (snapshot inmutable).
- 200: `{ "id", "ejercicio", "tipo", "fecha_generacion", "total_debe", "total_haber", "lineas": [ { "cuenta_id", "codigo", "nombre", "nivel", "debe", "haber", "saldo" } ], "sha256" }`
- 404: periodo inexistente o de otra empresa (aislamiento).

## Cierre anual

### POST `/api/v1/cierres/anual`
Ejecutar el cierre anual completo de un ejercicio de la empresa activa: valida periodos intermedios cerrados, genera el asiento de regularización (cuentas de resultados), el asiento de cierre y bloquea el ejercicio (`is_closed`); planifica/invoca la apertura del siguiente ejercicio (SPEC-009). Atómico e idempotente.
- Body: `{ "ejercicio": 2026 }`
- Reglas: todos los periodos intermedios del ejercicio deben estar `cerrado`/`cerrado_ajustado`; si falla cualquier paso, no queda ningún cambio parcial.
- 201: `{ "cierre_id", "ejercicio", "estado": "completado", "resultado_ejercicio", "asiento_regularizacion_id", "asiento_cierre_id", "asiento_apertura_id" }`
- 404: ejercicio inexistente en la empresa activa.
- 409: ejercicio ya cerrado | periodos intermedios sin cerrar | ejercicio con cuentas anuales formuladas (SPEC-010).
- 422: cuerpo inválido, ejercicio fuera de rango definido.

### GET `/api/v1/cierres/anual/{ejercicio}`
Detalle del cierre anual de un ejercicio de la empresa activa.
- 200: `{ "cierre_id", "ejercicio", "estado", "resultado_ejercicio", "asiento_regularizacion_id", "asiento_cierre_id", "asiento_apertura_id", "cerrado_at" }`
- 404: ejercicio inexistente o cierre no existente en la empresa activa.

## Reapertura controlada

### POST `/api/v1/cierres/reaperturas`
Solicitar la reapertura de un periodo (mes/trimestre) o de un ejercicio completo ya cerrado.
- Body: `{ "ejercicio": 2026, "tipo_periodo": "MES" | "TRIMESTRE" | "ANUAL", "periodo": 2, "motivo": "Error de imputación detectado en asiento n.º 3", "nota_impacto": "..." }`
- Reglas: `motivo` obligatorio; una sola solicitud activa por periodo; rechazo automático si el ejercicio está legalizado/formulado (SPEC-010) o IS liquidado (SPEC-023) sin nota de impacto.
- 201: `{ "solicitud_id", "numero_solicitud", "ejercicio", "estado": "pendiente", "fecha_solicitud" }`
- 403: rol sin permiso de solicitud de reapertura (SPEC-015).
- 404: periodo o ejercicio inexistentes en la empresa activa.
- 409: ya existe solicitud activa para el periodo | ejercicio legalizado/formulado | periodo no cerrado.
- 422: `motivo` vacío | `tipo_periodo`/`periodo` inválidos.

### POST `/api/v1/cierres/reaperturas/{solicitud_id}/aprobar`
Aprobar la solicitud (rol autorizado). El periodo pasa a disposición de reapertura.
- 200: `{ "solicitud_id", "estado": "aprobada", "aprobada_por", "fecha_aprobacion" }`
- 403: sin permiso de aprobación.
- 409: solicitud ya aprobada/rechazada/cerrada.

### POST `/api/v1/cierres/reaperturas/{solicitud_id}/rechazar`
Rechazar la solicitud con trazabilidad.
- 200: `{ "solicitud_id", "estado": "rechazada" }`

### POST `/api/v1/cierres/reaperturas/{solicitud_id}/rectificar`
Registrar el asiento de rectificación que completa el ajuste y provoca el re-cierre automático del periodo.
- Body: `{ "asiento_id": "<uuid>" }` (asiento previamente creado en SPEC-002 con `tipo` `ADJUSTMENT` o `REVERSAL` y fecha dentro del periodo reabierto).
- Reglas: el servicio verifica en la misma transacción que el asiento existe en la empresa activa, está POSTED, cuadra (Debe==Haber) y su fecha cae en el rango reabierto; enlaza `asiento_rectificacion_id`, pone `PeriodoCerrado.estado=cerrado_ajustado`, `n_reaperturas+1` y registra `fecha_cierre_efectivo`.
- 200: `{ "solicitud_id", "estado": "cerrada", "asiento_rectificacion_id", "fecha_cierre_efectivo" }`
- 404: solicitud o asiento inexistentes en la empresa activa.
- 409: asiento desbalanceado | asiento de otro tipo | fecha fuera de rango | solicitud no `reabierta`.
- 422: cuerpo inválido.

### GET `/api/v1/cierres/reaperturas`
Listado de solicitudes con filtros `ejercicio`, `estado`, `tipo_periodo`, paginación.
- 200: `{ "items": [ { "solicitud_id", "numero_solicitud", "ejercicio", "tipo_periodo", "periodo", "estado", "motivo", "fecha_solicitud", "asiento_rectificacion_id" } ], "total" }`

## Tratamiento de errores

- `401/403`: autenticación/permisos (SPEC-003/015); el 403 no revela existencia de datos de otras empresas.
- `404`: recurso inexistente en la empresa activa (nunca filtra datos de otra empresa).
- `409`: conflicto de estado (periodo ya cerrado, ejercicio cerrado, doble cierre, solicitud activa, ejercicio legalizado/formulado, IS liquidado).
- `422`: validación de negocio (importes, rangos, justificación, tipos).
- Importes siempre en precisión decimal; el backend es el único que valida partida doble.