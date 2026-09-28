# Quickstart Validation Guide: Plan General Contable (SPEC-001)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Requisitos previos: PostgreSQL 16+, Python 3.11+, Node.js 18+; seed mínimo (dos empresas A y B creadas por SPEC-003, o por SQL directo: `companies` + trigger `trg_companies_seed` que siembra `account_plan` con los 7 grupos). Referencias: [contracts](contracts/api-contracts.md), [data-model](data-model.md), plan raíz.

## Scenario 1 — Seeding automático y árbol de cuentas

```bash
# 1) Crear la empresa A (SPEC-003) → el trigger siembra el PGC base (7 grupos)
curl -X POST "$BASE/api/v1/companies" -H "Authorization: Bearer $TOK_A" \
  -d '{"nif":"A00000001","razon_social":"Empresa A S.L."}'

# 2) Consultar el árbol de la empresa activa
curl "$BASE/api/v1/accounts/tree" -H "Authorization: Bearer $TOK_A"
# Espera: 200; 7 nodos raíz con children; cada cuenta con level 1..5, is_selectable/is_active
```

Validación pytest:
- `test_seed_trigger_siembra_grupos`: crear empresa → 7 grupos de nivel 1 + subcuentas de nivel 4 con `is_selectable=true`.
- `test_seed_idempotente`: reintentar seed (o recrear con reintento) → no duplica.

## Scenario 2 — Autocompletar cuentas apuntables

```bash
curl "$BASE/api/v1/accounts/suggest?q=430" -H "Authorization: Bearer $TOK_A"
# Espera: 200, solo cuentas con is_selectable=true de la EMPRESA A (p. ej. 4300)

curl "$BASE/api/v1/accounts/suggest?q=zzzz" -H "Authorization: Bearer $TOK_A"
# Espera: 200 con items vacío (sin error)
```

Validación pytest:
- `test_suggest_solo_apuntables`: grupos/subgrupos (niveles 1-3) NUNCA aparecen; hojas nivel ≥ 4 sí.
- `test_suggest_aislamiento`: empresa B con cuentas coincidentes no las expone en A.

## Scenario 3 — Alta de subcuenta

```bash
curl -X POST "$BASE/api/v1/accounts" -H "Authorization: Bearer $TOK_A" \
  -H "Content-Type: application/json" \
  -d '{"code":"43000001","name":"Cliente Acme S.L.","parent_id":"<id_de_4300>"}'
# Espera: 201, level=5, is_selectable=true; 4300 pasa a is_selectable=false (trigger)

curl -X POST "$BASE/api/v1/accounts" -H "Authorization: Bearer $TOK_A" \
  -d '{"code":"43000001","name":"Cliente duplicado","parent_id":"<id_de_4300>"}'
# Espera: 409 código ya existente en la empresa
```

Validación pytest:
- `test_alta_hereda_jerarquia` y `test_alta_madre_deja_de_ser_apuntable`.
- `test_alta_codigo_duplicado` → 409; `test_alta_nivel5_rechazada` → 422; `test_alta_padre_otra_empresa` → 403/404.

## Scenario 4 — Edición y protección de cuentas

```bash
curl -X PATCH "$BASE/api/v1/accounts/<id_cuenta_sin_asientos>" \
  -H "Authorization: Bearer $TOK_A" -H "Content-Type: application/json" \
  -d '{"is_active":false}'
# Espera: 200, is_active=false

curl -X PATCH "$BASE/api/v1/accounts/<id_cuenta_con_asientos>" \
  -H "Authorization: Bearer $TOK_A" -d '{"is_active":false}'
# Espera: 409 "la cuenta tiene imputaciones" (SC-004)
```

Validación pytest:
- `test_proteccion_desactivacion_con_asientos` → 409 a nivel API y EXCEPTION a nivel DB (trigger `chk_account_plan_protected`).
- `test_editar_cuenta_otra_empresa` → 404 (no filtra datos de B).

## Scenario 5 — Aislamiento multi-empresa (constitución III)

```bash
# Empresa A ve su árbol / cuentas
curl "$BASE/api/v1/accounts/tree" -H "Authorization: Bearer $TOK_A"

# Consulta forzada de una cuenta de la Empresa B desde la sesión de A
curl -X PATCH "$BASE/api/v1/accounts/<id_cuenta_B>" -H "Authorization: Bearer $TOK_A" \
  -d '{"name":"hack"}'
# Espera: 404 — ningún dato de la Empresa B es observable

# Empresa B (sin relación con cuenta de A) intenta consultar el árbol con contexto inválido
curl "$BASE/api/v1/accounts/tree" -H "Authorization: Bearer $TOK_B" \
  -H "X-Empresa-Activa: <id_empresa_A_no_autorizada>"  # (o token sin reclamación)
# Espera: 403
```

Validación pytest:
- `test_tenant_isolation_tree`: el árbol de A jamás devuelve nodos de B.
- `test_tenant_isolation_by_id`: operación sobre ID de otra empresa → 404/403 sin información.
- `test_cross_tenant_full_flow`: A consulta/sugiere/crea/edit on B → todos rechazados.