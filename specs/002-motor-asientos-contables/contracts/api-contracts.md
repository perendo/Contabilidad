# API Contracts: Motor de Asientos Contables (SPEC-002)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Estilo: REST bajo **`/api/v1`**. La empresa activa se deriva **exclusivamente de la sesión/cabecera autenticada** (definida en SPEC-003); **nunca** se acepta `empresa_id`/`tenant_id` en path ni body. Importes siempre como **strings decimales** (p. ej. `"123.4500"`), nunca números de coma flotante. Errores estándar: `401`, `403`, `404`, `409`, `422`.

## Asientos

### POST `/api/v1/journal/entries`
Crear un asiento **en borrador (DRAFT)** con sus líneas.
- Body: `{ "fecha": "YYYY-MM-DD", "concepto": "…", "lineas": [ { "account_id": "…", "debit": "100.0000", "credit": "0.0000", "detail": "…"? } ] }`
- Reglas: mínimo dos líneas con al menos un Debe y un Haber; `sum(debit) == sum(credit)` exacto (4 decimales canónicos); cada `account_id` de la empresa activa, `is_selectable = true` e `is_active = true`; `ejercicio` derivado de `fecha` existente y no cerrado; no usa número (se asigna al asentar).
- 201: `{ "id", "estado": "DRAFT", "fecha", "concepto", "lineas": [ { "account_id", "debit", "credit" } ], "suma_debe": "…", "suma_haber": "…" }`
- 422: desbalanceado (`suma_debe != suma_haber`), una sola línea, cuenta no apuntable, precisión > 4 decimales, importes negativos. 400: fecha sin ejercicio o ejercicio cerrado. 403: cuenta de otra empresa en las líneas.

### POST `/api/v1/journal/entries/{id}/post`
Asentar el asiento: valida de nuevo balance/cuentas/ejercicio y asigna `numero` correlativo por (empresa, ejercicio) de forma **atómica** en la misma transacción.
- 200: `{ "id", "estado": "POSTED", "numero": 5, "ejercicio": 2026 }`
- 409: ya asentado; 404: inexistente en la empresa activa; 400: ejercicio cerrado.

### GET `/api/v1/journal/entries?date_from={yyyy-mm-dd}&date_to={yyyy-mm-dd}&page={n}&page_size={n}`
Libro diario de la empresa activa (solo `POSTED`/`CANCELLED`), orden `(fecha, numero)` asc, filtro de fechas **obligatorio**.
- 200: `{ "total": 42, "page": 1, "page_size": 20, "items": [ { "id", "numero", "fecha", "concepto", "estado", "tipo", "suma_debe": "…", "suma_haber": "…", "lineas": n } ] }`
- 422: rango de fechas ausente o invertido.

### GET `/api/v1/journal/entries/{id}`
Detalle con líneas y, si procede, el asiento de anulación asociado (`reversal_of_id`).
- 200: `{ "id", "numero", "fecha", "concepto", "estado", "tipo", "reversal_of_id", "creado_por", "created_at", "lineas": [ { "line_no", "account_id", "account_code", "account_name", "debit", "credit", "detail" } ] }`
- 404: inexistente, o pertenece a otra empresa (no se distingue).

## Anulación

### POST `/api/v1/journal/entries/{id}/reverse`
Anular un asiento `POSTED`: genera en la misma transacción un asiento `REVERSAL` con los **importes invertidos** (Debe ⇄ Haber), `reversal_of_id = {id}` y número correlativo; el original pasa a `CANCELLED` sin otra modificación.
- Body: `{ "fecha": "YYYY-MM-DD"?, "concepto": "Anulación de asiento {numero}"? }` (por defecto fecha actual y concepto por defecto).
- 201: `{ "id_reversal": "…", "numero_reversal": 6, "estado_original": "CANCELLED", "balance": { "suma_debe": "…", "suma_haber": "…" } }` (siempre balanceado, neto cero).
- 409: asiento no `POSTED` o ya `CANCELLED` (doble anulación) — la operación no crea duplicados. 404: inexistente en la empresa activa. 400: ejercicio cerrado para la fecha del rectificativo.

## Tratamiento de errores (resumen)

| Código | Escenario |
|--------|-----------|
| 401 | Sesión no autenticada o expirada |
| 403 | Sin acceso a la empresa del contexto (o cabecera de empresa ausente) |
| 404 | Asiento/account inexistente en la empresa activa (otra empresa → 404, sin revelar existencia) |
| 409 | Conflicto de estado: asiento ya asentado, doble anulación, `UNIQUE (empresa, ejercicio, numero)` |
| 422 | Validación de negocio: desbalance, líneas inválidas, cuenta no apuntable, precisión > 4 decimales, rango de fechas mal formado |
| 400 | Fecha sin ejercicio definido o ejercicio cerrado (SPEC-004) |

**Notas de seguridad**: la API nunca acepta `empresa_id` desde el cliente; el balance lo valida siempre el backend (y el trigger DB), la UI es solo informativa; los asientos `POSTED`/`CANCELLED` no tienen endpoints de update/delete.