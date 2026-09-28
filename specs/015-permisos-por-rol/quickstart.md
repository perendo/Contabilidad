# Quickstart Validation Guide: Matriz de Permisos por Rol (SPEC-015)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Requisitos previos: PostgreSQL 16+, Python 3.11+, Node.js 18+; SPEC-003 operativo (identidad, sesión, empresa activa, roles base sembrados por creación de empresa: ADMIN, ACCOUNTANT, READ_ONLY). Contratos en [contracts/](contracts/), modelo en [data-model.md](data-model.md).

## Scenario 1 — Ver el catálogo y la matriz de la empresa activa

```bash
# 1) Consultar el catálogo (ADMIN de la empresa A)
curl "$BASE/api/v1/permisos/catalogo" -H "Authorization: Bearer $TOK_ADMIN_A"
# Espera: 200, modulos: acct (ver/crear/editar/aprobar/importar_exportar/configurar), ...

# 2) Consultar la matriz inicial de la empresa A
curl "$BASE/api/v1/permisos/matriz" -H "Authorization: Bearer $TOK_ADMIN_A"
# Espera: 200, items con el seed (ADMIN → ver/crear/editar/en toda la empresa; ACCOUNTANT → ver/crear/editar; READ_ONLY → ver)
```

Validación pytest:
- `test_catalogo_semilla`: el catálogo contiene los módulos y operaciones esperados (D1 research).
- `test_matriz_seed_por_empresa`: la matriz inicial de A es la del seed de SPEC-003 y no contiene filas de B.

## Scenario 2 — Denegación por defecto (sin matriz explícita)

```bash
# 1) Usuario READ_ONLY intenta crear un asiento (SPEC-002) → módulo acct/crear
curl -X POST "$BASE/api/v1/asientos" -H "Authorization: Bearer $TOK_RO_A" -d '{"...":"..."}'
# Espera: 403 {"detail":"sin_permiso"} — aun sin fila de concesión, denegado por defecto

# 2) La denegación queda auditada
curl "$BASE/api/v1/permisos/auditoria?resultado=deny" -H "Authorization: Bearer $TOK_ADMIN_A"
# Espera: item con usuario RO, módulo acct, operacion crear, motivo sin_permiso, timestamp_utc, ip
```

Validación pytest:
- `test_denegacion_por_defecto`: cualquier operación sin fila en la matriz → 403.
- `test_denegacion_auditada`: la denegación genera `EventoAuditoriaAcceso` en la misma transacción.
- `test_operacion_inexistente`: pedir un permiso no catálogo → 403 `operacion_inexistente` + evento.

## Scenario 3 — Conceder y verificar

```bash
# 1) ADMIN concede a ACCOUNTANT el aprobado de asientos
curl -X POST "$BASE/api/v1/permisos/matriz" -H "Authorization: Bearer $TOK_ADMIN_A" \
  -d '{"rol_id":"<rol_acct_A>","modulo":"acct","operacion":"aprobar"}'
# Espera: 201, concedido=true

# 2) El usuario ACCOUNTANT ya puede aprobar (SPEC-002)
curl -X POST "$BASE/api/v1/asientos/{id}/aprobar" -H "Authorization: Bearer $TOK_ACCT_A"
# Espera: 200 — el rol ahora lo tiene concedido

# 3) Auditoría del permiso concedido sobre datos contables
curl "$BASE/api/v1/permisos/auditoria?resultado=allow" -H "Authorization: Bearer $TOK_ADMIN_A"
# Espera: item con módulo acct, operación aprobar, motivo concedido
```

Validación pytest:
- `test_concesion_auditada`: el allow sobre un asiento genera evento (FR-005).
- `test_concesion_duplicada`: segunda concesión del mismo (rol, permiso, empresa) → 409.
- `test_revocacion_inmediata`: DELETE de la fila → la siguiente petición es 403 (sin cacheo, D3 research).

## Scenario 4 — Restricción multiempresa (estricta)

```bash
# 1) El mismo rol ACCOUNTANT (mismo usuario) tiene permiso en la empresa A...
curl -X POST "$BASE/api/v1/permisos/matriz" -H "Authorization: Bearer $TOK_ADMIN_A" \
  -d '{"rol_id":"<rol_acct_A>","modulo":"acct","operacion":"aprobar"}'

# 2) ...pero en la empresa B NO está concedido
curl -X POST "$BASE/api/v1/asientos/{id}/aprobar" -H "Authorization: Bearer $TOK_USER_AB" \
  # sesión sobre empresa B
# Espera: 403 — la matriz de B no lo concede aunque el rol global lo parezca

# 3) El administrador de A no toca la matriz de B
curl -X GET "$BASE/api/v1/permisos/matriz" -H "Authorization: Bearer $TOK_ADMIN_A" # sobre empresa B
# Espera: 403/404 — nunca expone ni muta la matriz de otra empresa
```

Validación pytest:
- `test_matriz_aislada_por_empresa`: mismo rol en A vs B → A concede, B deniega (constitución III).
- `test_sin_acceso_cross_tenant`: la administración de la matriz de A desde B → 404; el usuario de A no ve roles de B.

## Scenario 5 — Ocultar UI según permisos (informativo)

```bash
curl "$BASE/api/v1/permisos/mis-permisos" -H "Authorization: Bearer $TOK_RO_A"
# Espera: 200, rol READ_ONLY, solo operaciones "ver"
# La UI oculta los módulos sin permiso; nunca confía en esto para seguridad (verificación en backend)
```

Validación pytest:
- `test_mis_permisos_por_empresa`: READ_ONLY de A no recibe los permisos concedidos a ACCOUNTANT de A ni ninguno de B.

## Scenario 6 — Administrador sin privilegio global

```bash
# El rol ADMIN en su empresa NO puede ejecutar operaciones fuera de la matriz de su empresa
curl -X POST "$BASE/api/v1/permisos/matriz" -H "Authorization: Bearer $TOK_ADMIN_B" \
  -d '{"rol_id":"<rol_admin_A>","modulo":"acct","operacion":"aprobar"}'
# No existe rol_admin_A en la empresa B (SPEC-003) → 422/404; nunca se concede sobre la empresa A
```

Validación pytest:
- `test_admin_sin_privilegio_global`: el ADMIN no excede la matriz de su empresa; no hay superusuario global (Assumptions spec).