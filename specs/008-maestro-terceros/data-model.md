# Data Model: Maestro de Terceros (Clientes y Proveedores) (SPEC-008)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Reglas transversales (constitución):
- Toda tabla incluye `empresa_id BIGINT NOT NULL` en PK/índices y filtros; se deriva de sesión.
- Importes en `NUMERIC(18,4)`/`Decimal`; prohibido `float`.
- Cada escritura se persiste con su registro de auditoría en la misma transacción ACID.

## Tercero

Ficha única del cliente y/o proveedor (por empresa).

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | parte de PK compuesta (empresa_id, id) |
| nif | VARCHAR(9) | CIF/NIF/NIE validado (algoritmo español); único por (empresa_id, nif) |
| razon_social | VARCHAR(200) | nombre o razón social |
| es_cliente | BOOLEAN | |
| es_proveedor | BOOLEAN | al menos uno TRUE; puede ser ambos |
| direcciones | JSONB | array de direcciones (tipo, dirección, CP, ciudad, provincia) |
| telefono | VARCHAR(20) | opcional |
| correo | VARCHAR(120) | opcional, formato email |
| iban | VARCHAR(34) NULL | validado MÓDULO 97; obligatorio para remesas SEPA (SPEC-020) |
| banco | VARCHAR(120) NULL | entidad bancaria (informativo) |
| autofactura | BOOLEAN DEFAULT FALSE | TRUE si NIF == NIF de la empresa |
| activo | BOOLEAN DEFAULT TRUE | FALSE = inactivado (baja suave) |
| creado_por / created_at / updated_at | | auditoría |

**Validaciones**: NIF único por (empresa_id, nif); formato NIF/CIF validado antes de persistir; IBAN (si presente) válido según ISO 13616 (MÓDULO 97); cambio de NIF con movimientos requiere permiso de administrador (SPEC-003/015) y queda auditado.

## TerceroSubcuenta

Relación tercero → subcuenta contable del plan de la empresa (asignación automática).

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| tercero_id | UUID FK → Tercero | |
| tipo | ENUM | `CLIENTE` / `PROVEEDOR` |
| cuenta_codigo | VARCHAR(20) | FK → CuentaContable (SPEC-001); subcuenta bajo 430/431 (cliente) o 410/411 (proveedor) |
| fecha_asignacion | DATE | |

**Validaciones**: una única subcuenta activa por (empresa_id, tercero_id, tipo); la cuenta debe existir en el plan de la empresa activa y ser de la clase 4 (deudores/acreedores).

## CondicionProntoPago

Condiciones de pronto pago por tercero (T-08/FR-009, entrada SPEC-020).

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| tercero_id | UUID FK → Tercero | |
| plazo_dias | INT | > 0 |
| porcentaje | NUMERIC(5,2) | 0 < % <= 100 |
| vigente | BOOLEAN | |
| override_factura_id | UUID FK NULL → SPEC-007 Factura | override por factura si aplica |

**Validación**: un único registro vigente por (empresa_id, tercero_id); si `override_factura_id` no es nulo, la condición aplica solo a esa factura.

## Movimientos y saldo (derivados, no persistidos)

El histórico y el saldo pendiente del tercero se **derivan** en la consulta agregando los datos existentes:

- **Facturas** (SPEC-007): `Factura` con `tercero_id` del tercero — estados emitida/anulada.
- **Asientos** (SPEC-002): `JournalEntryLine` cuya `cuenta` es la subcuenta del tercero (`TerceroSubcuenta.cuenta_codigo`).
- **Vencimientos** (SPEC-011): vencimientos del tercero con su estado.
- **Saldo pendiente**: `Σ importe vencimientos no liquidados` en `Decimal`.

## Resumen de relaciones

```
Tercero 1 ── n TerceroSubcuenta (CLIENTE / PROVEEDOR)
Tercero 1 ── n CondicionProntoPago (una vigente)
Tercero 1 ── n Factura (SPEC-007)
Tercero 1 ── n Vencimiento (SPEC-011)
CuentaContable (SPEC-001) 1 ── n TerceroSubcuenta.cuenta_codigo

Retirada: borrado físico solo si no hay Factura/JournalEntryLine/Vencimiento; si hay movimientos → solo `activo = FALSE` (inactivación).
```