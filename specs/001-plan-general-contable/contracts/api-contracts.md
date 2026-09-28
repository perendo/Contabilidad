# API Contracts: Plan General Contable (SPEC-001)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md) | **Fuente**: plan.md raíz §8

Estilo: REST bajo **`/api/v1`**. La empresa activa se deriva **exclusivamente de la sesión/cabecera autenticada** (cabecera `X-Empresa-Activa` o reclamación del token definida en SPEC-003); **nunca** se acepta `tenant_id`/`empresa_id` en path ni en body. Respuestas JSON; sin importes en esta feature (no aplica). Errores estándar: `401` (sin sesión), `403` (sin acceso al tenant), `404` (recurso inexistente en la empresa activa — nunca filtra datos de otra empresa), `409` (conflicto de estado/protección), `422` (validación de negocio).

## Árbol de cuentas

### GET `/api/v1/accounts/tree`
Árbol de cuentas de la empresa activa (hasta 5 niveles).
- Respuesta 200: `{ "nodos": [ { "id", "code", "name", "level", "is_selectable", "is_active", "children": [ ... ] } ] }`
- Reglas: solo cuentas de la empresa activa; plano de cuentas vacío → `{ "nodos": [] }` sin error; cada nodo indica visualmente `is_active=false` y `is_selectable=true` (FR-010).
- 403 si el contexto de empresa no pertenece a la sesión.

## Autocompletar

### GET `/api/v1/accounts/suggest?q={fragmento}&limit={n}`
Sugerencias de cuentas **apuntables** por fragmento de código o nombre.
- Query: `q` (obligatorio, ≥ 1 carácter), `limit` (opcional, default 20, max 50).
- Respuesta 200: `{ "items": [ { "id", "code", "name", "level", "is_selectable": true } ] }`
- Reglas: solo `is_selectable = true` e `is_active = true` de la empresa activa; matchea prefijo de `code` y fragmento de `name` (índice pg_trgm); sin coincidencias → lista vacía sin error (FR-003/SC-002 < 1 s).

## Alta de cuentas y subcuentas

### POST `/api/v1/accounts`
Alta de una cuenta (nivel 1 sin `parent_id`) o subcuenta (con `parent_id`).
- Body: `{ "code": "43000001", "name": "Cliente Acme S.L.", "parent_id": "…" }` (`parent_id` opcional).
- Reglas: código único por empresa (409 si `UNIQUE (tenant_id, code)`); nivel = `length(code)` (1-4) o 5-8 dígitos; rechazo si nivel padre + 1 supera 5 (422); padre inexistente o de otra empresa → 404/403; al crear una hija, la madre deja de ser apuntable (trigger); la nueva cuenta es apuntable si es hoja de nivel ≥ 4; entrada de auditoría en la misma transacción.
- 201: `{ "id", "code", "name", "level", "is_selectable", "is_active" }`
- 409: código ya existente en la empresa activa. 422: nivel máximo superado / código mal formado. 404: padre inexistente. 403: padre de otra empresa.

## Edición de cuentas

### PATCH `/api/v1/accounts/{id}`
Editar `name` y/o `is_active`.
- Body: `{ "name": "…"?, "is_active": true|false? }` (al menos un campo).
- Reglas: cuenta de la empresa activa (si no existe en el tenant → 404); desactivación bloqueada si la cuenta tiene imputaciones en `journal_entry_line` o tiene hijas → 409 con mensaje comprensible (SC-004); renombrado a un `name` ya usado en la empresa → 409; entrada de auditoría en la misma transacción.
- 200: `{ "id", "code", "name", "level", "is_selectable", "is_active", "updated_at" }`
- 409: cuenta con asientos asociados o nombre duplicado. 404: cuenta inexistente en la empresa activa.

## Tratamiento de errores (resumen)

| Código | Escenario |
|--------|-----------|
| 401 | Sesión no autenticada o expirada |
| 403 | Contexto de empresa no autorizado para la sesión (o cabecera de empresa ausente) |
| 404 | Recurso inexistente en la empresa activa (incluye la cuenta de otra empresa — no se distingue de "no existe") |
| 409 | Código/nombre duplicado en la empresa; desactivación de cuenta con imputaciones/hijas |
| 422 | Validación de negocio (código no numérico, nivel/longitud inconsistente, nivel 5 con hijas, `q` vacío) |

**Notas de seguridad**: la API nunca acepta `tenant_id`/`empresa_id` desde el cliente; toda query/escritura se aplica sobre el `tenant_id` derivado de la sesión; el backend (y los triggers DB) es la única autoridad de apuntabilidad y protección.