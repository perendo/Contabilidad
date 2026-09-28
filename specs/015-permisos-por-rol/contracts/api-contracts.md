# API Contracts: Matriz de Permisos por Rol (SPEC-015)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Estilo: REST bajo `/api/v1/...` (los endpoints exigen la cabecera de sesión autenticada; el **`empresa_id` activo se deriva EXCLUSIVAMENTE de la cabecera de sesión** — nunca viaja en path ni en body). Respuestas JSON; sin importes monetarios en este módulo. La identidad y el rol del usuario provienen de **SPEC-003**; esta API gestiona la matriz y consulta el log de accesos. Un recurso de otra empresa → `404`. No aplican formatos de fichero externos.

## Catálogo de operaciones

### GET `/api/v1/permisos/catalogo`
Listado del catálogo `PermisoOperacion` (solo la empresa activa puede consultarlo; requiere `rbac`/`ver`).
- 200: `{ "modulos": [ { "modulo": "acct", "operaciones": ["ver","crear","editar","aprobar","importar_exportar","configurar"] } ], "total" }`

## Matriz de permisos

### GET `/api/v1/permisos/matriz`
Matriz de la empresa activa (requiere `rbac`/`ver` sobre configuración).
- 200: `{ "items": [{ "rol_id", "rol": "ACCOUNTANT", "modulo", "operacion", "permiso_id" }], "roles": ["ADMIN","ACCOUNTANT","READ_ONLY"] }`

### POST `/api/v1/permisos/matriz`
Conceder una operación a un rol en la empresa activa (requiere `rbac`/`configurar`).
- Body: `{ "rol_id", "modulo": "acct", "operacion": "aprobar" }`
- Reglas: inserta fila `(empresa_id, rol_id, permiso_id)`; ausencia previa = denegado; crea `EventoAuditoriaAcceso` en la misma transacción.
- 201: `{ "matriz_id", "rol_id", "modulo", "operacion", "concedido": true }`
- 409: concesión ya existente; 422: operación o rol inexistente (`operacion_inexistente`).

### DELETE `/api/v1/permisos/matriz/{matriz_id}`
Revocar una concesión (elimina la fila; a partir de ese instante → denegado). Requiere `rbac`/`configurar`.
- 204; 404 si no pertenece a la empresa activa.

### POST `/api/v1/permisos/matriz/reset`
Restablecer la matriz inicial de la empresa (seed de SPEC-003) — idempotente, audita el cambio.
- Body: `{ "confirm": true }`
- 200: `{ "concesiones": n }`

## Autorización (dependency central)

No expuesta como recurso REST propio; se aplica a **cada** operación de cualquier router mediante la dependency `require_permission(modulo, operacion)`:

- Falta de sesión → `401` (SPEC-003).
- Empresa activa sin rol → `403` con `EventoAuditoriaAcceso` (`motivo: sin_rol`).
- Operación sin concesión en la empresa activa → `403` (`motivo: sin_permiso`) + evento auditado.
- Operación inexistente en el catálogo → `403` (`motivo: operacion_inexistente`) + evento auditado.
- `403` nunca revela información de otra empresa (constitución III).

## Auditoría de accesos

### GET `/api/v1/permisos/auditoria`
Eventos de acceso de la empresa activa (filtro `resultado`, `modulo`, `operacion`, `usuario_id`, `fecha[gte/lte]`, paginación). Requiere `rbac`/`ver`.
- 200: `{ "items": [{ "usuario_id", "rol_id", "modulo", "operacion", "resultado": "allow"|"deny", "motivo", "timestamp_utc", "ip" }], "total" }`

### GET `/api/v1/permisos/mis-permisos`
Operaciones que el rol del usuario tiene concedidas en la empresa activa (la UI lo usa para ocultar módulos; la seguridad no depende de esto).
- 200: `{ "rol": "READ_ONLY", "permisos": [{ "modulo", "operacion" }] }`

## Tratamiento de errores

- `401/403`: autenticación (SPEC-003) / denegación por matriz (motivo en auditoría).
- `404`: recurso inexistente en la empresa activa (nunca filtra datos de otra empresa; nada revela la existencia de matrices de otras empresas).
- `409`: conflicto de estado (concesión duplicada).
- `422`: validación de negocio (rol/operación inexistentes, payload malformado).
- Sin importes monetarios; la auditoría de accesos cuelga de la transacción ACID de cada operación sobre datos contables (FR-005).