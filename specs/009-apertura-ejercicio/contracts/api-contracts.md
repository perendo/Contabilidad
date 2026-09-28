# API Contracts: Apertura del Ejercicio (SPEC-009)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Estilo: REST bajo `/api/v1/...` (empresa activa derivada de sesión en cabecera; `empresa_id` nunca en body/path como dato de selección). Respuestas JSON; importes como strings decimales (p. ej. `"1234.5600"`), nunca números de coma flotante.

## Apertura del Ejercicio

### POST `/api/v1/ciclo/apertura`
Abrir el ejercicio siguiente generando el asiento de apertura balanceado.
- Body: `{ "ejercicio_destino": 2027 }` (año del ejercicio a abrir)
- Reglas: valida que el ejercicio anterior (2026) esté cerrado, el destino no tenga apertura, y el rango de fechas esté definido. Genera `JournalEntry` de tipo `OPENING` con líneas de saldos patrimoniales, Debe==Haber verificado.
- 201: `{ "asiento_id", "numero_asiento", "ejercicio_destino", "fecha", "n_lineas", "importe_total_debe", "importe_total_haber" }`
- 409: `ejercicio_cerrado` (el ejercicio anterior no está cerrado), `ejercicio_ya_abierto` (ya existe asiento de apertura), `ejercicio_no_definido` (rango de fechas no creado).
- 422: `asiento_desbalanceado` (error de cálculo), `cuentas_patrimoniales_vacias`.

### GET `/api/v1/ciclo/apertura/estado`
Consultar el estado de apertura del ejercicio activo.
- Query params: `ejercicio` (año, opcional; por defecto el actual).
- 200: `{ "ejercicio", "estado", "asiento_apertura_id" | null, "fecha_generacion" | null }`

### POST `/api/v1/ciclo/apertura/anular`
Anular la apertura del ejercicio activo generando un asiento REVERSAL.
- Body: `{ "ejercicio": 2027, "motivo": "Saldos incorrectos del cierre anterior" }`
- Reglas: genera `JournalEntry` de tipo `OPENING_REVERSAL` enlazado al asiento `OPENING` original. El original permanece inmutable. Se permite regenerar la apertura después.
- 200: `{ "asiento_reversal_id", "numero_asiento", "asiento_original_id", "estado" }`
- 409: `sin_apertura` (no hay apertura que anular), `ejercicio_cerrado` (no se puede anular si el ejercicio destino está cerrado).

### POST `/api/v1/ciclo/apertura/regenerar`
Regenerar la apertura del ejercicio tras una anulación previa.
- Body: `{ "ejercicio_destino": 2027 }`
- Reglas: requiere que el ejercicio anterior esté cerrado y exista un `OPENING_REVERSAL` previo (o el `OPENING` haya sido anulado). Genera un nuevo `OPENING` con saldos recalculados.
- 201: `{ "asiento_id", "numero_asiento", "ejercicio_destino", "n_lineas" }`
- 409: `apertura_activa` (ya existe un asiento de apertura activo para ese ejercicio), `ejercicio_cerrado`.

## Tratamiento de errores

- `401/403`: autenticación/permisos (SPEC-003).
- `404`: recurso inexistente en la empresa activa.
- `409`: conflicto de estado (ejercicio cerrado, apertura duplicada, doble apertura).
- `422`: validación de negocio (desbalance, cuentas vacías).
