# Research: Facturación Operativa (SPEC-007)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Resoluciones de los unknowns del Technical Context y decisiones de diseño conforme a la constitución y al plan raíz.

## D1. Estructura del documento de factura

- **Decision**: La factura se modela como cabecera (`Factura`) + líneas (`FacturaLinea`) + desglose de impuestos derivado (IVA, IRPF, recargo de equivalencia). Cada línea contiene `base`, `tipo_iva`, `tipo_recargo`, `tipo_irpf` y `importe`. Los totales de la cabecera se derivan por agregación de las líneas al confirmar.
- **Rationale**: El modelo cabecera + líneas alinea con el modelo de asiento (SPEC-002) y permite facturas N:M con distintos tipos de IVA.
- **Alternatives considered**: Factura con un único impuesto global (pierde al detalle, no soporta líneas heterogéneas); esquema XML nativo (sobre-ingeniería para esta fase).

## D2. Cálculo de impuestos y manejo de Decimal

- **Decision**: El cálculo de IVA/IRPF/recargo se realiza en `Decimal` con contexto de alta precisión, redondeando **línea a línea** a 2 decimales a nivel de documento fiscal. Cada línea calcula `cuota_iva = base * tipo_iva`, `irpf = base_irpf * tipo_irpf`, `recargo = base * tipo_recargo` con `Decimal`. La suma de cuotas línea a línea es el total de impuestos de la factura.
- **Rationale**: Cumple FR-002/FR-008 y la norma constitucional; el redondeo línea a línea evita discrepancias de precisión y coincide con la práctica contable española (LIVA/ajuste de redondeo).
- **Alternatives considered**: Redondeo en el total (puede diferir de la suma de líneas y generar discrepancias con el asiento); usar `float` para impuestos (viola constitución).

## D3. Recargo de equivalencia (FR-010)

- **Decision**: Si la empresa está en régimen de recargo de equivalencia, cada línea calcula además la cuota de recargo: `cuota_recargo = base * tipo_recargo` (tipos vigentes: 5,2 % general, 1,4 % reducido y superreducido, 0,5 % productos manufacturados). El desglose contabiliza la cuota en **cuenta separada del IVA** (477/472 recargo) y el asiento resultante mantiene la precisión decimal exacta.
- **Rationale**: La aclaración integrada FR-010 exige cuota separada y cuenta contable propia; es la práctica PGC y de la AEAT.
- **Alternatives considered**: Sumar el recargo al IVA en la misma cuenta (pierde la trazabilidad fiscal exigida); configurar recargo por serie (innecesario).

## D4. Criterio de caja (FR-011)

- **Decision**: Si la empresa opera en régimen de criterio de caja, la factura se emite con el **IVA íntegro** (base + cuota), pero el impuesto queda marcado como **diferido**: se contabiliza el IVA con su saldo pendiente de liquidación y SPEC-012 (libros de IVA) gestionará el devengo al producirse el cobro/pago. La factura almacena `régimen_caja = TRUE` y `devenido = FALSE`; al cobrar, SPEC-012 lo revierte.
- **Rationale**: La aclaración integrada FR-011 establece que el régimen de caja difiere el devengo dejando el IVA en 477/472 con saldo pendiente hasta el cobro/pago.
- **Alternatives considered**: Emitir la factura con IVA diferido 0 (incorrecto fiscalmente — la factura lleva IVA íntegro); sin marcado de diferimiento (SPEC-012 no podría gestionarlo).

## D5. Vínculo factura-asiento (patrón integrado)

- **Decision**: El asiento contable se genera en la **misma transacción ACID** que persiste la factura emitida (`async with async_session.begin()`), con `Factura.asiento_id` FK. Asiento típico de venta: Debe 430 (clientes) | Haber 700 (ventas), 477 (IVA) y, si procede, 477/472 (recargo) y 475/473 (IRPF retenido si aplica). Para compras: Debe 600/601… y 472 (IVA) | Haber 410 (proveedores), 475 (IRPF).
- **Rationale**: Sigue la asunción de la spec ("el enlace factura-asiento usa el patrón integrado (misma transacción)"); garantiza que no existe factura sin asiento.
- **Alternatives considered**: Asiento generado en segundo plano/worker (rompe la atomicidad); asiento sin enlace FK (pierde trazabilidad).

## D6. Numeración correlativa por serie y ejercicio

- **Decision**: La numeración es correlativa por `(empresa_id, serie_id, ejercicio)`, con **reserva indefinida de números anulados** (un número anulado no se reutiliza). La asignación ocurre dentro de la misma transacción que emite la factura, sobre secuencia bloqueada (`SELECT ... FOR UPDATE` de contador por (empresa, serie, ejercicio) o secuencia PostgreSQL).
- **Rationale**: Cumple constitución IV y FR-003; la reserva de anulados es requisito fiscal español (T-02).
- **Alternatives considered**: Numeración sin reserva (rompe trazabilidad fiscal); numeración global por empresa (impide series independientes).

## D7. Rectificación de facturas (abono)

- **Decision**: La factura rectificativa se genera con `tipo = RECTIFICATIVA`, `factura_original_id` FK al original y numeración propia correlativa en su serie. El asiento de anulación invierte las líneas del asiento original (Debe↔Haber) como en SPEC-006, creando un `JournalEntry` nuevo de tipo `REVERSAL` sin tocar el original. Se admite rectificación sobre una factura ya rectificada enlazando a la original.
- **Rationale**: Cumple constitución II y FR-005; la inversión de líneas mantiene la consistencia del diario.
- **Alternatives considered**: Eliminar la factura emitida (viola inmutabilidad); rectificativo solo a nivel fiscal sin asiento (pierde la contabilidad).

## D8. Estados y ciclo de vida de la factura

- **Decision**: Estados `borrador`, `emitida`, `anulada`. Una factura `borrador` puede eliminarse o editarse; al confirmar pasa a `emitida` (irreversible, genera asiento y número). Una `emitida` solo puede rectificarse (crea RECTIFICATIVA) o anularse (si tiene rectificativa que la anula totalmente); nunca se borra. La emisión con fecha en ejercicio cerrado se rechaza (400).
- **Rationale**: Cumple FR-006/FR-007 y el edge case "una vez emitida no se borra".
- **Alternatives considered**: Estado `pagada` en factura (pertenece a SPEC-011 cobros/pagos, no aquí).

## D9. Configuración de IVA/IRPF por empresa

- **Decision**: La configuración de impuestos (tipos y cuentas 477/472/475/473/700/600) vive en una etapa de configuración previa por empresa (SPEC-001) que esta feature consume. El módulo es opt-in por empresa: si no está configurado, el módulo de facturación no está disponible.
- **Rationale**: Sigue la asunción de la spec; la configuración previa evita errores de cuenta en la generación del asiento.
- **Alternatives considered**: Configuración embebida en la factura (duplica configuración fiscal); cuentas globales (rompe multi-tenancy).

## D10. Integración con el maestro de terceros (SPEC-008)

- **Decision**: La factura referencia `tercero_id` (SPEC-008) con su rol cliente/proveedor. Las subcuentas 430/410 del tercero se usan como cuentas de Debe/Haber del asiento de facturación. Si el tercero no existe, la emisión se bloquea.
- **Rationale**: Cumple T-06 y la dependencia de SPEC-008; garantiza coherencia maestro ↔ facturación.
- **Alternatives considered**: Tercero embebido en la factura (duplica datos, rompe coherencia con 430/410).