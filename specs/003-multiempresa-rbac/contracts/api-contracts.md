# API Contracts: Multiempresa y Control de Acceso por Roles (SPEC-003)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Estilo: REST bajo **`/api/v1`**. La empresa activa se deriva **exclusivamente** de la cabecera `X-Empresa-Activa` validada contra la sesión; **nunca** se acepta `empresa_id`/`tenant_id` en path ni body. Errores estándar: `401`, `403`, `404`, `409`, `422`. Las empresas retornadas son únicamente las accesibles y activas del usuario autenticado.

## Login

### POST `/api/v1/auth/login`
Autenticar al usuario y devolver su sesión con empresas accesibles.
- Body: `{ "email": "…", "password": "…" }`
- 200: `{ "token": "<jwt>", "user": { "id", "email", "full_name" }, "default_company_id": "<company_id>", "companies": [ { "company_id", "nif", "razon_social", "role": "ADMIN"|"ACCOUNTANT"|"READ_ONLY", "is_default": true|false } ] }`
- 401: credenciales inválidas o usuario inactivo; no se revela si el email existe.
- Auditoría: `LOGIN` (éxito) o `LOGIN_FAILED` (fallo, solo actor + email hash + IP, sin revelar existencia).

## Sesión

### GET `/api/v1/auth/me`
Devolver la sesión del usuario autenticado y sus empresas accesibles (actualizada con la empresa activa actual).
- 200: `{ "user": { "id", "email", "full_name" }, "companies": [...], "default_company_id": "…" }`
- 401: token ausente o expirado.

### POST `/api/v1/auth/switch-company`
Cambiar la empresa activa sin re-login. El cliente debe renovar su cabecera `X-Empresa-Activa` con la respuesta.
- Body: `{ "company_id": "…" }`
- Reglas: la empresa debe estar en la lista de empresas accesibles y activas del usuario; si no → 403 y la empresa activa permanece sin cambios (FR-004/FR-009).
- 200: `{ "company_id": "…", "razon_social": "…", "role": "…" }`
- 403: el usuario no tiene relación activa con la empresa solicitada.

## Empresas

### GET `/api/v1/companies`
Listar solo las empresas accesibles y activas del usuario (FR-005).
- 200: `{ "items": [ { "company_id", "nif", "razon_social", "role", "is_default" } ] }`

### POST `/api/v1/companies`
Crear una nueva empresa. El usuario queda como `ADMIN` y se inicializa su plan de cuentas base (`seed_default_pgc` de SPEC-001 en la misma transacción ACID).
- Body: `{ "nif": "…", "razon_social": "…" }`
- Reglas: la empresa aparece inmediatamente en la lista del usuario con rol `ADMIN`; el PGC base se siembra dentro de la misma transacción; si el seed falla, la empresa no se crea (atomicidad).
- 201: `{ "company_id", "nif", "razon_social", "role": "ADMIN", "default_company_id": "…" }`
- 409: si el nombre/cif fuera duplicado (tras futura validación; en esta feature se acepta).
- Auditoría: `CREATE_COMPANY` en la misma transacción.

## Empresa activa (cómo se transporta)

| Dónde | Cómo |
|-------|------|
| **Backend (FastAPI)** | La empresa activa se extrae de la cabecera `X-Empresa-Activa` en cada petición de datos; el guard `get_empresa_id()` la valida contra la relación `user_companies` activa del usuario; sin cabecera o sin relación → 403. |
| **Frontend (Next.js)** | La empresa activa se mantiene en estado global; se envía como cabecera `X-Empresa-Activa` en **todas** las peticiones a los endpoints de datos (cuentas, asientos, informes, facturas); al cambiar, se actualiza el estado y las llamadas posteriores llevan el contexto nuevo (SC-003). |
| **Nunca** | El `empresa_id`/`tenant_id` no viaja en **path**, **query param** ni **body** de ninguna petición de datos. |

## Guards (reglas de seguridad por endpoint)

| Guard | Descripción | Errores |
|-------|-------------|---------|
| `get_current_user` | Valida JWT, extrae `user_id`; token ausente/expirado o usuario inactivo → deniega | 401 |
| `get_empresa_id` | Extrae `X-Empresa-Activa`, valida relación activa con el usuario | 403 |
| `require_role(ADMIN, ACCOUNTANT)` | Exige rol específico sobre la empresa activa | 403 (sin detalles) |
| `require_write` | Cualquier endpoint de escritura bloquea `READ_ONLY` | 403 |

## Tratamiento de errores (resumen)

| Código | Escenario |
|--------|-----------|
| 401 | Token ausente/expirado; credenciales incorrectas; usuario inactivo |
| 403 | Sin acceso a la empresa del contexto; empresa solicitada sin relación activa; rol insuficiente; empresa inactiva |
| 404 | Recurso inexistente (no se aplica directamente aquí pero integra con las otras features) |
| 409 | Conflicto de estado (empresa ya creada con el mismo NIF, en su caso) |
| 422 | Email mal formado, contraseña vacía, `company_id` ausente en switch |

**Notas de seguridad**: la lista de empresas de un usuario jamás incluye empresas inactivas; el `switch-company` revalida contra la DB en cada petición; un usuario desactivado pierde acceso inmediatamente.