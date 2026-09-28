# API Contracts: Amortizaciones del Inmovilizado (SPEC-014)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Estilo: REST bajo `/api/v1/...` (los endpoints exigen la cabecera de sesión autenticada; el **`empresa_id` activo se deriva EXCLUSIVAMENTE de la cabecera de sesión** — nunca viaja en path ni en body). Respuestas JSON; importes como strings decimales (p. ej. `"1500.0000"`), nunca coma flotante. Un recurso de otra empresa → `404`. No aplican formatos de fichero externos (no hay import/export en esta feature).

## Activos

### POST `/api/v1/activos`
Dar de alta un activo de inmovilizado (cuenta 21x del plan de la empresa activa).
- Body: `{ "numero_activo", "cuenta_id", "descripcion", "fecha_alta": "YYYY-MM-DD", "coste_amortizable": "15000.0000", "vida_util": 60, "metodo": "lineal" | "regresivo", "porcentaje_regresivo"?, "cuenta_gasto_id"?, "cuenta_acumulada_id"? }`
- Reglas: valida la cuenta 21x (grupos 681/281 por defecto), calcula y valida el plan completo de amortización; persistencia en transacción ACID con audit.
- 201: `{ "id", "numero_activo", "cuenta_id", "coste_amortizable", "metodo", "estado": "en_uso", "plan": [{ "ejercicio", "periodo", "cuota", "acumulado" }] }`
- 422: importes/campos inválidos (cuota acumulada > coste, porcentaje fuera de rango, fecha en ejercicio cerrado).

### GET `/api/v1/activos`
Listado con filtros `estado`, `cuenta_id`, `ejercicio_alta`, paginación.
- 200: `{ "items": [{ "id", "numero_activo", "descripcion", "cuenta_id", "coste_amortizable", "metodo", "estado", "amortizado_acumulado" }], "total" }`

### GET `/api/v1/activos/{id}`
Detalle del activo con su plan.
- 200: `{ ...activo, "plan": [{ "ejercicio", "periodo", "cuota", "acumulado", "estado": "pendiente"|"amortizado" }] }`
- 404 si no pertenece a la empresa activa.

### PATCH `/api/v1/activos/{id}`
Editar un activo (descripción, vida útil, coste, método) — **no** toca asientos ya `POSTED`.
- Reglas: recalcula el **plan futuro** desde el próximo período usando el acumulado ya posteado (constitución II); valida que ninguna cuota futura exceda el nuevo coste.
- 200: `{ ...activo, "plan_futuro": [...] }` — los asientos previos quedan intactos.
- 409: intentar editar un activo `dado_de_baja` o cambiar la cuenta del activo con acumulado.

## Plan y generación

### POST `/api/v1/activos/{id}/plan/calcular`
Calcular (sin persistir) el plan de un activo con los parámetros propuestos.
- Body: los mismos campos de alta.
- 200: `{ "plan": [{ "ejercicio", "periodo", "cuota", "acumulado" }], "total_amortizable": "15000.0000", "error_si_excede"? }`

### POST `/api/v1/amortizaciones/generar`
Generar los asientos de amortización del período (681 contra 281).
- Body: `{ "ejercicio": 2026, "periodo": 10 }`
- Reglas: ejercicio **abierto** (SPEC-004); crea un asiento por activo pendiente; `AmortizacionGenerada` único por (activo, ejercicio, periodo); marca `PlanAmortizacion → amortizado`; todos en una transacción ACID con audit.
- 200: `{ "generados": [{ "activo_id", "asiento_id", "cuota" }], "n": k, "omisiones": [{ "activo_id", "motivo" }] }`
- 409: ejercicio cerrado; período ya generado (antiduplicado).

### GET `/api/v1/amortizaciones`
Registros de amortización generados (filtro `ejercicio`, `periodo`, `activo_id`, paginación).
- 200: `{ "items": [{ "activo_id", "asiento_id", "ejercicio", "periodo", "cuota" }], "total" }`

### POST `/api/v1/amortizaciones/{id}/reabrir`
Reabrir un período ya amortizado (con trazabilidad).
- Body: `{ "motivo" }`
- Reglas: genera un `REVERSAL` del asiento previo (constitución II), desmarca el plan y permite regenerar; `reapertura_de` del nuevo `AmortizacionGenerada` apunta al previo.
- 200: `{ "reversal_asiento_id", "estado": "pendiente" }`
- 409: si el período pertenece a un ejercicio cerrado.

## Bajas

### POST `/api/v1/activos/{id}/baja`
Registrar la baja/venta de un activo.
- Body: `{ "fecha_baja": "YYYY-MM-DD", "precio_venta": "8000.0000", "tipo": "venta" | "retirada" }`
- Reglas: prorratea la amortización hasta la fecha de baja (config de empresa); calcula acumulado, VNC y resultado; genera asiento balanceado (Debe 281 + 572/570; Haber 21x; saldo → 671/771); activo → `dado_de_baja`.
- 201: `{ "baja_id", "amortizacion_hasta_baja", "valor_neto_contable", "resultado", "asiento_id" }`
- 404/409: activo inexistente en la empresa activa o ya dado de baja; ejercicio cerrado a la fecha de baja → 409.

## Tratamiento de errores

- `401/403`: autenticación/permisos (SPEC-003; permisos por operación ver SPEC-015).
- `404`: recurso inexistente en la empresa activa (nunca filtra datos de otra empresa).
- `409`: conflicto de estado (ejercicio cerrado, período ya amortizado, activo ya dado de baja, edición de activo con asientos posteados).
- `422`: validación de negocio (importes, porcentaje, cuota que excede coste, fechas).
- Importes siempre en precisión decimal; los asientos los genera y valida el motor de SPEC-002 (Debe==Haber); nunca se actualiza ni borra un `JournalEntry` `POSTED`.