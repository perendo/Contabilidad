# Research: Remesas SEPA y Soporte Magnético (SPEC-020)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Resoluciones de los unknowns del Technical Context y decisiones de diseño conforme a la constitución y al plan raíz.

## D1. Formato de fichero de domiciliación (SEPA vs CSB 19.19)

- **Decision**: Generar **ambos** formatos: XML SEPA DD `PAIN.008.001.02` con tipo de adeudo **CORE** (predeterminado) y **B2B** opcional por tercero, y soporte magnético **AEB CSB 19.19**. Selección de formato por remesa.
- **Rationale**: Las entidades bancarias españolas exigen SEPA desde 2014, pero muchas aún operan con CSB 19.19 para recibos SEPA sin XML; mantener ambos maximiza compatibilidad y cumple la aclaración de la sesión 2026-09-16.
- **Alternatives considered**: Solo SEPA (pierde bancos legacy); solo 19.19 (incumple estándar EPC). El CORE es el esquema por defecto del EPC con protección al deudor; B2B requiere mandato firmado y sin derecho a rechazo posterior.

## D2. Tipos de adeudo y plazos de presentación

- **Decision**: El tipo se define por tercero/mandato (CORE o B2B). La **fecha de cargo = fecha de vencimiento** de cada recibo; una remesa puede contener varias fechas y el fichero crea un grupo por fecha y tipo. Validar antes de emitir: primera domiciliación **CORE** con anticipación mínima **D-2 días hábiles**, CORE recurrente según mandato/banco, y **B2B** **D-1 día hábil** con mandato previo autorizado.
- **Rationale**: Es la regla EPC del SEPA Core Direct Debit Rulebook (art. 5.1: latest presentación) y del B2B Rulebook.
- **Alternatives considered**: Fecha configurable por remesa (añade riesgo de rechazos); sin validación (produce rechazos bancarios R19).

## D3. Merienda de mandatos y datos bancarios

- **Decision**: El **IBAN** y las **condiciones de pronto pago** se alojan en el maestro de terceros (SPEC-008, ampliada con T-08/FR-009). Para adeudos **B2B** se requiere **mandato SEPA** (identificador de mandato, fecha/firma, cesionario) almacenado como entidad propia `MandatoSepa`.
- **Rationale**: La normativa SEPA exige mandatos firmados para todos los adeudos (CORE y B2B); para B2B el mandato es condición de validez del fichero.
- **Alternatives considered**: Guardar mandato en el tercero (mezcla una entidad de garantía con el dato comercial); se descartó por trazabilidad.

## D4. Confirmación de cobro (manual / conciliación)

- **Decision**: El recibo remesado pasa a **cobrado** por marcado manual del usuario o detección de movimiento en la conciliación bancaria (**SPEC-013**). Ambos caminos usan una clave idempotente y no pueden crear dos asientos. No hay descarga automática de confirmaciones del banco en esta feature.
- **Rationale**: Evita ampliar el alcance a integración bancaria; mantiene la spec coherente (FR-007).
- **Alternatives considered**: Confirmación vía fichero de abonos bancarios (crédito); se difiere a la evolución de SPEC-013/029.

## D5. Devoluciones R19/C19

- **Decision**: El procesado de una devolución (rechazo **R19**/baja **C19**) normaliza códigos de hasta 10 caracteres, genera un asiento **`REVERSAL`** del cobro (Debe 430 más 626 si hay gastos; Haber 572/570 por el total), **reabre el vencimiento** a pendiente y crea la `DevolucionRecibo` con su `Reclamacion`. El asiento original no se modifica (constitución II) y el identificador externo del retorno impide reprocesados.
- **Rationale**: Cualquier impago debe revertirse con un asiento nuevo balanceado y trazable.
- **Alternatives considered**: Solo reapertura informativa (deja el asiento del cobro sin reversar → descuadre); se descartó.

## D6. Descuento por pronto pago

- **Decision**: Condiciones (plazo en días y %) por **tercero** (SPEC-008) con override por factura; aplica solo si el pago ocurre dentro del plazo. Asiento: **432 (clientes, descuentos s/ventas por pronto pago)** o **662 (descuentos s/ventas por pronto pago)** contra **430**; el neto nunca es negativo y se calcula con `Decimal`.
- **Rationale**: El pronto pago es un acuerdo comercial por deudor; la cuenta 432/662 es el tratamiento PGC estándar.
- **Alternatives considered**: Condición global por empresa (poco realista); por factura a mano (alto esfuerzo).

## D7. Correlatividad del número de remesa

- **Decision**: `numero_remesa` correlativo por **empresa + ejercicio**, asignado **dentro de la misma transacción ACID** que persiste la remesa, sobre secuencia bloqueada (`SELECT ... FOR UPDATE` de un contador o secuencia `BIGSERIAL` por (empresa, ejercicio)).
- **Rationale**: Cumple constitución IV; impide duplicados/omisiones bajo concurrencia.
- **Alternatives considered**: Número por tenant global (rompe correlatividad contable por ejercicio).

## D8. Precisión y estructura del fichero

- **Decision**: Todos los importes del fichero (base, cuota, importe) y de los asientos se serializan en `NUMERIC(18,4)`/`Decimal`, formateados sin coma flotante. En CSB 19.19 los importes se emiten sin decimales en moneda EUR con divisor (importe en céntimos) en el campo correspondiente; en SEPA el importe se indica con 2 decimales obligatorios del esquema EPC.
- **Rationale**: La aritmética del dominio prohíbe `float`; el esquema PAIN.008 exige `Amount` con hasta 2 decimales.
- **Alternatives considered**: Formateo en frontend (descarta precision en backend); se rechaza.

## D9. Stack e integración

- **Decision**: Backend **FastAPI async + SQLAlchemy async + asyncpg** en los servicios de `treasury/`; generadores de fichero como servicios puros (sin estado) que reciven el modelo ya persistido; frontend Next.js llama al API con la cabecera de empresa activa.
- **Rationale**: Coherencia con la constitución y el `plan.md` raíz; las reglas de negocio se ejecutan en el backend.
- **Alternatives considered**: Generar el fichero en el frontend (excluye validaciones de backend y la correlatividad); se descarta.