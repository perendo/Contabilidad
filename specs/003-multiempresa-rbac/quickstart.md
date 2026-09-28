# Quickstart Validation Guide: Multiempresa y Control de Acceso por Roles (SPEC-003)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Requisitos previos: PostgreSQL 16+, Python 3.11+, Node.js 18+; seed mínimo (base de datos vacía; la creación de la empresa provoca el seed del PGC automáticamente). Referencias: [contracts](contracts/api-contracts.md), [data-model](data-model.md).

## Scenario 1 — Login con empresa por defecto

```bash
# 1) Login con credenciales válidas
curl -X POST "$BASE/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"contador@empresaA.es","password":"Secret123!"}'
# Espera: 200, token JWT, default_company_id != null, companies con role "ADMIN" (por crear la empresa)
```

Validación pytest:
- `test_login_credenciales_validas`: devuelve token, lista de empresas y empresa por defecto.
- `test_login_credenciales_invalidas`: 401 sin revelar datos.

## Scenario 2 — Crear empresa con seed del PGC

```bash
curl -X POST "$BASE/api/v1/companies" \
  -H "Authorization: Bearer $TOK" \
  -H "Content-Type: application/json" \
  -d '{"nif":"A12345678","razon_social":"Nueva Empresa S.L."}'
# Espera: 201; company_id nuevo, role="ADMIN", y GET /api/v1/accounts/tree devuelve los 7 grupos del PGC
```

Validación pytest:
- `test_crear_empresa_seed_pgc`: crear empresa → el usuario tiene rol ADMIN y `GET /accounts/tree` retorna ≥ 7 nodos raíz; la empresa aparece en la lista del usuario.
- `test_seed_atomico`: si el seed falla, la empresa no persiste (transacción revertida).

## Scenario 3 — Cambiar empresa activa sin re-login

```bash
# Asumimos que el usuario tiene acceso a empresa A y empresa B
curl -X POST "$BASE/api/v1/auth/switch-company" \
  -H "Authorization: Bearer $TOK" \
  -d '{"company_id":"<empresa_B>"}'
# Espera: 200, company_id=empresa_B, role="ACCOUNTANT"

# Inmediatamente: consultar cuentas → solo las de B
curl "$BASE/api/v1/accounts/tree" -H "Authorization: Bearer $TOK" -H "X-Empresa-Activa: <empresa_B>"
```

Validación pytest:
- `test_switch_company_actualiza_contexto`: tras switch, las cuentas/asientos devueltos son los de la nueva empresa (SC-002/SC-003).
- `test_switch_company_sin_acceso`: empresa no relacional → 403; empresa activa permanece.

## Scenario 4 — Denegación 403 en empresa no autorizada

```bash
# Operar con empresa no relacional
curl "$BASE/api/v1/accounts/tree" -H "Authorization: Bearer $TOK" -H "X-Empresa-Activa: <empresa_C_no_autorizada>"
# Espera: 403 sin datos de empresa_C
```

Validación pytest:
- `test_403_empresa_no_autorizada`: GET accounts/tree con empresa no relacional → 403; no se filtra ningún dato de la empresa no autorizada.
- `test_403_sin_cabecera_empresa`: petición sin cabecera `X-Empresa-Activa` → 403 (no existe operación sin empresa).

## Scenario 5 — READ_ONLY bloqueado en escrituras

```bash
# Un usuario con rol READ_ONLY intenta crear una cuenta
curl -X POST "$BASE/api/v1/accounts" \
  -H "Authorization: Bearer $TOK_READONLY" -H "X-Empresa-Activa: <empresa_A>" \
  -d '{"code":"9999","name":"test"}'
# Espera: 403 (role READ_ONLY bloqueado en escrituras)
```

Validación pytest:
- `test_read_only_bloqueado_escritura`: READ_ONLY → 403 en POST/PATCH de cuentas; solo puede GET.

## Scenario 6 — Aislamiento completo multi-empresa (constitución III)

```bash
# Crear empresa A y empresa B por distintos usuarios; cruzar acceso
curl -X POST "$BASE/api/v1/auth/login" -d '{"email":"a@test.es","password":"…"}'
curl -X POST "$BASE/api/v1/auth/switch-company" -d '{"company_id":"<empresa_B>"}'
# → 403; empresa activa permanece A

# Operatoria de empresa B desde sesión A → 404 (accounts, journal entries, reports)
curl "$BASE/api/v1/accounts/tree" -H "X-Empresa-Activa: <empresa_B>"  # → 403
curl "$BASE/api/v1/journal/entries?date_from=2026-01-01&date_to=2026-12-31" -H "X-Empresa-Activa: <empresa_B>"  # → 403
```

Validación pytest:
- `test_tenant_isolation_full`: ninguna operación cross-empresa (cuentas, asientos, informes) retorna datos; todas retornan 403 o 404.