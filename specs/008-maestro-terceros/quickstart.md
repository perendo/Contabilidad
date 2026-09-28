# Quickstart Validation Guide: Maestro de Terceros (Cliente y Proveedores) (SPEC-008)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Requisitos previos: PostgreSQL 16+, Python 3.11+, Node.js 18+; seed mínimo (empresa + plan de cuentas con cuentas 430/431/410/411 de clase 4).

## Scenario 1 — Alta de tercero con subcuentas automáticas

```bash
# 1) Dar de alta un cliente y proveedor
curl -X POST "$BASE/api/v1/terceros" \
  -H "Authorization: Bearer $TOK" \
  -H "Content-Type: application/json" \
  -d '{
    "nif": "B12345678", "razon_social": "ACME Servicios S.L.",
    "es_cliente": true, "es_proveedor": true,
    "direcciones": [{"tipo": "FISCAL", "direccion": "C/ Mayor 1", "cp": "28001", "ciudad": "Madrid", "provincia": "Madrid"}],
    "telefono": "912345678", "correo": "contacto@acme.es",
    "iban": "ES9121000418450200051332", "banco": "Banco de Madrid"
  }'
# Espera: 201, subcuentas CLIENTE (43000001) y PROVEEDOR (41000001) asignadas automáticamente
```

Validación pytest:
- `test_alta_tercero_subcuentas`: verificar creación del tercero y sus 2 subcuentas en el plan.
- `test_alta_tercero_auditoria`: verificar registro de auditoría del alta.

## Scenario 2 — NIF duplicado y NIF inválido

```bash
# Alta del mismo NIF en la misma empresa
curl -X POST "$BASE/api/v1/terceros" ... # nif B12345678
# Espera: 409 "Ya existe un tercero con NIF B12345678 en esta empresa"

# Alta con NIF mal formado
curl -X POST "$BASE/api/v1/terceros" -d '{"nif":"ABC123","razon_social":"Inválido",...}'
# Espera: 422 "NIF/CIF inválido"
```

Validación pytest:
- `test_duplicado_nif_empresa`: misma empresa → 409; otra empresa → 201 (aislamiento por empresa).
- `test_nif_invalido`: NIF con formato incorrecto → 422.

## Scenario 3 — Validación IBAN

```bash
# Alta con IBAN inválido
curl -X POST "$BASE/api/v1/terceros" -d '{"iban":"ES0000000000000000000000",...}'
# Espera: 422 "IBAN inválido"

# Alta sin IBAN (permitido, pero excluido de remesas SEPA)
# → 201, iban=null
```

Validación pytest:
- `test_iban_invalido`: IBAN roto → 422.
- `test_iban_optativo`: sin IBAN se permite (operará sin remesas SEPA).

## Scenario 4 — Ficha con saldo pendiente derivado

```bash
# Tras crear factura de SPEC-007 o vencimiento de SPEC-011 para el tercero:
curl "$BASE/api/v1/terceros/$TER_ID" -H "Authorization: Bearer $TOK"
# Espera: 200, saldo_pendiente="1500.0000", facturas y vencimientos del tercero listados
```

Validación pytest:
- `test_saldo_derivado_decimal`: creación de vencimientos → saldo_pendiente exacto en Decimal.
- `test_saldo_solo_empresa_activa`: movimientos de otra empresa no afectan el saldo.

## Scenario 5 — Retirada y protección de baja

```bash
# Retirar tercero con movimientos → solo inactiva
curl -X POST "$BASE/api/v1/terceros/$TER_ID/retirar" \
  -H "Authorization: Bearer $TOK" \
  -d '{"eliminar": true}'
# Espera: 409 "El tercero tiene movimientos: solo se puede inactivar"

# Inactivar sin eliminar
curl -X POST "$BASE/api/v1/terceros/$TER_ID/retirar" \
  -d '{"eliminar": false}'
# Espera: 200, activo=false

# Borrar físicamente un tercero sin movimientos
curl -X DELETE "$BASE/api/v1/terceros/$TER_ID_SIN_MOV"
# Espera: 204
```

Validación pytest:
- `test_baja_con_movimientos_bloqueada`: tercero con factura/asiento/vencimiento → 409.
- `test_inactivacion_conserva_historico`: inactivar conserva facturas y asientos del tercero.
- `test_baja_fisica_sin_movimientos`: sin movimientos → borrado OK.

## Scenario 6 — Condiciones de pronto pago (T-08/FR-009 para SPEC-020)

```bash
# Crear condición vigente
curl -X POST "$BASE/api/v1/terceros/$TER_ID/condiciones" \
  -H "Authorization: Bearer $TOK" \
  -d '{"plazo_dias": 10, "porcentaje": "2.00", "vigente": true}'
# Espera: 201

# Intentar crear segunda vigente → 409
curl -X POST "$BASE/api/v1/terceros/$TER_ID/condiciones" \
  -d '{"plazo_dias": 15, "porcentaje": "1.50", "vigente": true}'
# Espera: 409 "Ya existe una condición vigente para este tercero"

# Consultar condiciones (SPEC-020 las consume en la liquidación)
curl "$BASE/api/v1/terceros/$TER_ID/condiciones" -H "Authorization: Bearer $TOK"
# Espera: 200, items con la condición vigente
```

## Scenario 7 — Aislamiento multi-empresa (constitución III)

```bash
# Alta del mismo tercero en empresa B → ficha aislada
curl -X POST "$BASE/api/v1/terceros" -d '{"nif":"B12345678",...}'
# Espera: 201 (cada empresa tiene su propia ficha)

# Consultar ficha de la empresa A desde la empresa B
curl "$BASE/api/v1/terceros/$TER_A" -H "Authorization: Bearer $TOK_B"
# Espera: 404

# Baja desde B del tercero de A
curl -X DELETE "$BASE/api/v1/terceros/$TER_A" -H "Authorization: Bearer $TOK_B"
# Espera: 404
```

Validación pytest:
- `test_aislamiento_empresa_terceros`: A no ve los terceros de B y viceversa (mismo NIF, fichas separadas).