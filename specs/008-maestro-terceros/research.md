# Research: Maestro de Terceros (Clientes y Proveedores) (SPEC-008)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Resoluciones de los unknowns del Technical Context y decisiones de diseño conforme a la constitución y al plan raíz.

## D1. Modelo de tercero (ficha única con roles)

- **Decision**: Un `Tercero` es una ficha única por empresa que puede tener **ambos roles** (cliente y proveedor) a la vez (`es_cliente`, `es_proveedor` BOOLEAN). Incluye NIF/CIF, razón social, direcciones (array), teléfonos, correos, y datos bancarios (IBAN/banco). La ficha es estrictamente por empresa (edge case "dos empresas comparten tercero → fichas aisladas").
- **Rationale**: Cumple el edge case "un tercero es a la vez cliente y proveedor → ficha única con ambos roles" y la asunción "el maestro es por empresa".
- **Alternatives considered**: Ficha global compartida entre empresas (rompe aislamiento multi-tenant const. III); dos fichas separadas por rol (duplica datos del mismo tercero).

## D2. Validación de NIF/CIF y unicidad

- **Decision**: El NIF/CIF se valida con el algoritmo español (letra de control NIF personas físicas; dígito/letra de CIF personas jurídicas; NIE con letra inicial). La **unicidad es por empresa** (`empresa_id`, `nif`): dos empresas pueden tener el mismo NIF en sendas fichas aisladas. Un NIF mal formado se rechaza con 422 antes de persistir.
- **Rationale**: Cumple FR-003 y el edge case "NIF mal formado"; cumple FR-001 (aislamiento) y la asunción de unicidad por empresa.
- **Alternatives considered**: Unicidad global de NIF (rompe multi-tenancy — mismo deudor en dos empresas); sin validación de formato (entrada sucia).

## D3. Asignación automática de subcuentas 430/410

- **Decision**: Al dar de alta un tercero, el sistema asigna **automáticamente** sus subcuentas dentro del plan de cuentas de la empresa: subcuenta de clientes bajo 430/431 (ventas) y de proveedores bajo 410/411 (compras), generadas según una **convención configurable** (p. ej., sufijo numérico secuencial por empresa bajo la cuenta 430). Se crea `TerceroSubcuenta` con la relación tercero↔cuenta.
- **Rationale**: Cumple FR-004 y T-03 ("subcuenta por NIF bajo la cuenta 430/431" según asunción); permite facturación (SPEC-007) y vencimientos (SPEC-011) sin fricción.
- **Alternatives considered**: Cuenta manual a elegir por el usuario (alto esfuerzo y errores); subcuenta por NIF directa (conflictos por longitud del código).

## D4. Ficha con histórico y saldo pendiente

- **Decision**: El saldo y el histórico del tercero NO se almacenan como tabla; se **derivan** por agregación de los movimientos contables existentes (asientos SPEC-002 con la subcuenta del tercero, facturas SPEC-007, vencimientos SPEC-011) en la consulta, con `Decimal`. La ficha expone: facturas (nº, fecha, importe, estado), cobros/pagos, vencimientos y saldo pendiente = suma de vencimientos no liquidados.
- **Rationale**: Evita redundancia y drift entre un agregado y los movimientos reales; el saldo siempre cuadra con el diario.
- **Alternatives considered**: Tabla de saldo materializado (riesgo de desincronización con el diario); saldo en el propio tercero (mismo problema).

## D5. Retirada y protección de la baja definitiva

- **Decision**: La **baja definitiva (borrado físico)** solo se permite si el tercero no tiene movimientos (ni asientos, facturas ni vencimientos). Si los tiene, se bloquea (409) y se sugiere la **inactivación** (`activo = FALSE`), que conserva el histórico. El borrado físico requiere vaciar el histórico (asunción de la spec) y se audita.
- **Rationale**: Cumple FR-006 y el edge case "con movimientos → bloquea la baja y sugiere inactivar"; protege la integridad del diario (const. II).
- **Alternatives considered**: Borrado suave siempre (anonima pero deja agujeros en auditoría); prohibición absoluta de baja (impide limpieza de maestros vacíos).

## D6. Datos bancarios y validación de IBAN (T-08/FR-009)

- **Decision**: El tercero lleva `iban` (VARCHAR 34) y `banco` (nombre/entidad opcional). El IBAN se valida con el **MÓDULO 97** (reordenación + comprobación) y el formato/país. Si el tercero no tiene IBAN puede operar en facturación y cobros manuales, pero **se excluye de las remesas SEPA** (SPEC-020), que lo exige para la inclusión (FR-009).
- **Rationale**: Cumple T-08/FR-009 y el edge case "tercero sin IBAN → excluido de remesas SEPA"; la validación módulo 97 es el estándar ISO 13616.
- **Alternatives considered**: Sin validación de IBAN (errores de domiciliación); IBAN obligatorio siempre (bloquea terceros de efectivo/contado).

## D7. Condiciones de pronto pago por tercero (T-08/FR-009)

- **Decision**: `CondicionProntoPago` por tercero con `plazo_dias INT`, `porcentaje NUMERIC(5,2)`, `vigente BOOLEAN` y `override_factura_id` opcional (SPEC-007). Un único registro vigente por (empresa_id, tercero_id). SPEC-020 la consume en la liquidación (432/662 contra 430) con cálculo en `Decimal` (`neto = importe × (1 − %/100)`, neto ≥ 0).
- **Rationale**: Cumple T-08/FR-009; modela el acuerdo comercial por deudor y es la base del descuento por pronto pago de SPEC-020.
- **Alternatives considered**: Condición global por empresa (el acuerdo es por deudor); condición sin override por factura (impide excepción puntual).

## D8. Cambio de NIF con trazabilidad

- **Decision**: El cambio del NIF del tercero se permite solo si el tercero no tiene movimientos; con movimientos exige **permiso de administrador** (SPEC-003/015) y se registra en auditoría el NIF anterior y el nuevo (payload inmutable). Igual para cambios de IBAN. La auditoría captura actor, timestamp UTC, IP, acción y payload en strings decimales.
- **Rationale**: Cumple el edge case "cambio de NIF con movimientos → solo con permiso de administrador, auditado" (const. auditoría).
- **Alternatives considered**: Prohibir el cambio de NIF siempre (impide corrección de datos); permitir libremente (rompe trazabilidad).

## D9. Autofactura (NIF = NIF de la empresa)

- **Decision**: Si el NIF del tercero coincide con el propio de la empresa, se valida el caso de **autofactura**: se registra el tercero con una marca `autofactura = TRUE` y validación específica (supuesto de diseño de la spec). Esto permite operaciones intraempresa sin romper la unicidad normal.
- **Rationale**: Cumple el edge case "NIF coincide con la empresa (autofactura) → asociado como tercero propio con validación específica".
- **Alternatives considered**: Rechazar NIF = empresa (bloquea autofacturas reales); tratar como tercero normal (pierde la marca específica).

## D10. Integración y stack

- **Decision**: Backend **FastAPI async + SQLAlchemy async + asyncpg** en `services/thirdparty/`; la ficha con saldo se sirve como agregado de consulta derivado (sin materializar). Frontend Next.js llama al API con la cabecera de empresa activa. SPEC-007 consume el tercero para facturación; SPEC-020 consume IBAN y condiciones para remesas.
- **Rationale**: Coherencia con la constitución y el `plan.md` raíz; reglas de negocio en backend.
- **Alternatives considered**: Saldo materializado en el tercero (drift); ficha consumida directamente desde el frontend (pierde validaciones backend).