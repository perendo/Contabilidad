# Research: Asientos Contables Multilínea (SPEC-006)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Resoluciones de los unknowns del Technical Context y decisiones de diseño conforme a la constitución y al plan raíz.

## D1. Modelo de datos para asientos multilínea

- **Decision**: No se crea una tabla nueva. Se **amplía** el modelo `JournalEntryLine` existente de SPEC-002 para que cada línea sea un apunte independiente (Debe o Haber) referenciado a una cabecera `JournalEntry`. Un asiento puede tener N líneas al Debe y M líneas al Haber; la distinción se hace por el campo `importe` (positivo = Debe, o bien un campo `tipo` ENUM `DEBE`/`HABER`). No se impone límite de dominio por lado.
- **Rationale**: El modelo relacional existente de cabecera + líneas es natural para N:M; no hay razón para crear una tabla separada.
- **Alternatives considered**: Tabla de asientos multilínea separada (duplica estructura, complica consultas); modelo pivotado (menos legible, no aporta nada).

## D2. Estrategia de validación del balance multilínea

- **Decision**: La validación de balance se ejecuta **antes** de persistir cualquier cosa. Se calcula `sum(debe for line in lines if debe > 0) == sum(haber for line in lines if haber > 0)` usando `Decimal` con contexto de alta precisión. Si hay alguna línea con ambos valores o sin ninguno, se rechaza. El cálculo se hace en el servicio `validador_multilinea.py` y se ejecuta en la transacción de persistencia.
- **Rationale**: Cumple constitución I y III; la validación en backend es la única fuente de verdad.
- **Alternatives considered**: Validación SQL ( CHECK constraint en la cabecera — no viable porque la suma depende de las líneas); validación por trigger (posible pero redundante con la del servicio).

## D3. Regla de los dos lados

- **Decision**: Todo asiento debe tener **al menos una línea con Debe > 0** y **al menos una línea con Haber > 0**. Si un lado está vacío, se rechaza con error claro `lado_vacio` ( tipo `DEBE` o `HABER`). Se valida antes de la transacción de persistencia.
- **Rationale**: Cumple FR-002 y la lógica contable básica: un asiento sin Debe o sin Haber no existe.
- **Alternatives considered**: Permitir un lado vacío para casos especiales (p. ej. asientos de ajuste internos) — se descarta por romper la partida doble.

## D4. Anulación/rectificativo de asientos multilínea

- **Decision**: Al anular un asiento multilínea (N débitos, M créditos), se genera un asiento rectificativo con **todas las líneas invertidas**: cada línea con `debe > 0` pasa a `haber = debe, debe = 0` y viceversa. El rectificativo contiene M débitos y N créditos (invertidos). El resultado neto es cero. El asiento original no se modifica (inmutabilidad). El rectificativo se enlaza al original con un campo `asiento_original_id` en `JournalEntry`.
- **Rationale**: Cumple constitución II y FR-005; la inversión de todas las líneas mantiene la consistencia del diario.
- **Alternatives considered**: Colapsar líneas repetidas (pierde trazabilidad); generar un único apunte neto por cuenta (no respeta la estructura original).

## D5. Precisión en la suma de muchas líneas

- **Decision**: La suma de hasta 100 líneas se calcula con `Decimal` en el contexto por defecto de Python (28 dígitos de precisión). No se usa `float` en ningún punto del acumulador. El balance debe cuadrar exactamente (diferencia == `Decimal("0")`).
- **Rationale**: Cumple la norma constitucional de precisión decimal; 100 líneas con 4 decimales no generan errores de redondeo en 28 dígitos.
- **Alternatives considered**: Redondeo explícito a 4 decimales antes de comparar (pierde precisión); tolerancia ε (inaceptable en contabilidad).

## D6. Límite práctico de líneas

- **Decision**: No se impone límite de dominio; el límite práctico se define en configuración (default **100 líneas por asiento**). Si se supera, se rechaza con error `limite_lineas_excedido`. El límite es configurable por empresa.
- **Rationale**: Un límite práctico evita abuso de memoria sin imponer restricciones de negocio innecesarias.
- **Alternatives considered**: Sin límite (riesgo de rendimiento); límite fijo en código (poco flexible).

## D7. Integración con importación/exportación (SPEC-005)

- **Decision**: Los archivos de importación de SPEC-005 admiten grupos multilínea (filas con el mismo `numero_asiento`). La exportación incluye todas las líneas de cada asiento, una por fila. La agrupación se gestiona en el parseador de SPEC-005; el motor de asientos de SPEC-006 recibe la lista completa de líneas validadas.
- **Rationale**: Cumple FR-008; la integración es natural dado que ambas features operan sobre las mismas entidades.
- **Alternatives considered**: Exportar un asiento multilínea en una sola fila (pierde detalle); no soportar multilínea en importación (restringe la utilidad de SPEC-005).

## D8. Entrada contable por teclado (frontend)

- **Decision**: El componente `LineEditor` del frontend ofrece filas dinámicas con: tecla `Enter` para añadir fila, `Tab` para moverse entre campos, `Shift+Tab` para retroceder, `Ctrl+Supr` para eliminar fila. El balance se muestra en tiempo real en la UI (informativo, nunca reemplaza la validación del backend). La UI muestra `totalDebe` y `totalHaber` y un indicador de balance.
- **Rationale**: Cumple la norma constitucional de entrada contable optimizada por teclado y FR-009.
- **Alternatives considered**: Interfaz con botones para añadir/eliminar filas (menos eficiente para entrada masiva).

## D9. Cuentas repetidas en un mismo asiento

- **Decision**: Se **admiten** líneas de la misma cuenta en el mismo asiento sin colapsarlas ni rechazarlas (FR-007). El efectivo neto por cuenta se deriva de su suma; esto es habitual en asientos compuestos (ej. un gasto parcialmente deducible).
- **Rationale**: Es una necesidad contable real; colapsar perdería la trazabilidad de las parcialidades.
- **Alternatives considered**: Rechazar cuentas duplicadas (poco práctico); colapsar automáticamente (pierde detalle).
