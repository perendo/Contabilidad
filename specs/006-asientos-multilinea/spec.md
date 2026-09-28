# Feature Specification: Asientos Contables Multilínea

**Feature Branch**: `006-asientos-multilinea`

**Created**: 2026-09-16

**Status**: Draft

**Input**: User description: "Haz el todos separados por numeros, asegurate que se puedan incluir asientos multiples (mas de una partida al debe y al haber)"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Registrar un asiento con varias partidas en ambos lados (Priority: P1)

El contador registra un asiento con más de una partida al Debe y más de una partida al Haber (p. ej., tres débitos y dos créditos) en una única operación. Todas las partidas se guardan a la vez y el asiento solo se acepta si la suma total del Debe es exactamente igual a la suma total del Haber.

**Why this priority**: Los asientos reales rara vez son 1 a 1; el soporte multilínea (N partidas por lado) es imprescindible para la contabilidad habitual y queda cubierto por la partida doble estricta de la constitución.

**Independent Test**: Registrando un asiento con 3 débitos y 2 créditos balanceados, se persisten las 5 partidas de forma indivisible; uno desbalanceado se rechaza entero.

**Acceptance Scenarios**:

1. **Given** un usuario autenticado de la empresa activa con cuentas apuntables, **When** registra un asiento con varias líneas al Debe y varias al Haber, **Then** todas las líneas se guardan de forma indivisible y el asiento queda balanceado (Sum Debe == Sum Haber).
2. **Given** un asiento multilínea cuya suma del Debe no es exactamente igual a la del Haber, **When** se intenta guardar, **Then** se rechaza sin persistir ninguna línea ni cabecera.

---

### User Story 2 - Registrar el asiento clásico de una partida por lado (Priority: P1)

El contador también debe poder registrar la forma clásica: una sola partida al Debe y una sola al Haber. El sistema trata ambos casos igual y siempre exige al menos una partida en cada lado.

**Why this priority**: El caso 1:1 sigue siendo el más frecuente; debe convivir con el multilínea sin fricción.

**Independent Test**: Registrando un asiento 1:1 balanceado, se guarda correctamente; registrando un asiento con un lado vacío, se rechaza.

**Acceptance Scenarios**:

1. **Given** un asiento con una sola partida al Debe y una sola al Haber, **When** se guarda, **Then** se acepta como caso válido con el balance estricto.
2. **Given** un asiento sin ninguna partida en el Debe o sin ninguna en el Haber, **When** se intenta guardar, **Then** el sistema lo rechaza indicando el lado que falta.

---

### User Story 3 - Anular un asiento multilínea (Priority: P2)

Cuando el contador anula un asiento ya asentado con varias partidas, el sistema genera el asiento rectificativo invirtiendo cada una de sus partidas (Debe <-> Haber), de modo que la suma neta quede en cero y ningún apunte quede sin contrapartida.

**Why this priority**: La anulación de un asiento multilínea debe replicar la misma estructura invertida para mantener la consistencia del diario (inmutabilidad de la constitución).

**Independent Test**: Anulando un asiento de 3 débitos y 2 créditos, el rectificativo contiene 2 débitos y 3 créditos invertidos y permanece balanceado.

**Acceptance Scenarios**:

1. **Given** un asiento asentado con N líneas al Debe y M líneas al Haber, **When** se anula, **Then** se genera un asiento rectificativo enlazado con todas las líneas invertidas y suma neta cero.
2. **Given** el asiento rectificativo generado, **When** se verifica su balance, **Then** Sum(Debe) == Sum(Haber) se cumple exactamente.

---

### User Story 4 - Importar y exportar asientos multilínea (Priority: P3)

El contador importa y exporta asientos que contienen varias partidas por lado mediante archivos (CSV/Excel), conservando todas y cada una de las líneas de ambos lados.

**Why this priority**: El procesamiento masivo no debe perder líneas al agrupar los apuntes por asiento.

**Independent Test**: Exportando un asiento multilínea e importándolo de vuelta, el número de partidas y su balance se conservan.

**Acceptance Scenarios**:

1. **Given** un asiento con varias partidas por lado, **When** se exporta, **Then** el archivo incluye todas las líneas de Debe y Haber sin pérdidas.
2. **Given** un archivo con grupos multilínea, **When** se previsualiza y se importa, **Then** todos los grupos válidos se guardan completos y los desbalanceados se marcan como error.

---

### Edge Cases

- ¿Qué ocurre con cero partidas en un lado? → Se rechaza el asiento: debe haber al menos una partida por lado.
- ¿Qué ocurre con un asiento de N débitos y 1 crédito? → Válido: no se impone simetría de cantidades, solo balance de sumas.
- ¿Qué ocurre si dos líneas usan la misma cuenta dentro del mismo asiento? → Admisible: pueden coexistir líneas de la misma cuenta; el efectivo neto por cuenta se deriva de su suma.
- ¿Qué ocurre al anular un asiento multilínea con cuentas repetidas? → Se invierten todas las líneas una a una, sin colapsar ni reordenar.
- ¿Qué ocurre durante la importación con un grupo multilínea dividido en varias secciones del archivo? → Se interpreta por agrupación del asiento; el criterio de agrupación se define en la plantilla (SPEC-005).
- ¿Qué ocurre con precisión al sumar muchas líneas? → Las sumas se calculan en precisión decimal canónica; el balance debe cuadrar exactamente.

## Requisitos (TODOs numerados)

1. **T-01** Modelo unificado de asiento multilínea: una cabecera con N líneas de Debe y M de Haber (sin límite fijo por lado).
2. **T-02** Validación estricta de balance con N partidas por lado: Sum(Debe) == Sum(Haber) en precisión decimal exacta.
3. **T-03** Regla de los dos lados: exigir al menos una partida en el Debe y una en el Haber; rechazo claro en caso contrario.
4. **T-04** Anulación/rectificativo multilínea: invertir todas las partidas (Debe <-> Haber) manteniendo estructura y balance; mantener la inmutabilidad del original.
5. **T-05** Entrada contable en la interfaz orientada a teclado con filas dinámicas para añadir varias partidas por lado.
6. **T-06** Pre-validación e importación masiva (CSV/Excel) de grupos multilínea sin pérdida de líneas.
7. **T-07** Exportación (CSV/Excel) del diario conservando todas las líneas de cada asiento.
8. **T-08** Pruebas automáticas (pytest) de: balance multilínea, rechazo con lado vacío, anulación invertida y persistencia 1:1 y N:M.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST admitir asientos con una o más (N) líneas al Debe y una o más (M) líneas al Haber de forma simultánea, sin límite fijo por lado.
- **FR-002**: El sistema MUST exigir al menos una partida en cada lado (Debe y Haber) y rechazar cualquier asiento con un lado vacío.
- **FR-003**: El sistema MUST aplicar el balance estricto multilínea: la suma de todas las partidas del Debe es exactamente igual a la suma de todas las partidas del Haber, calculada con precisión decimal canónica.
- **FR-004**: El sistema MUST persistir cabecera y todas las líneas (Debe y Haber) de un asiento de forma indivisible en una única transacción.
- **FR-005**: El sistema MUST permitir anular un asiento multilínea generando un asiento rectificativo con todas las líneas invertidas (N «M) y suma neta cero, enlazado al original.
- **FR-006**: El sistema MUST validar que todas las cuentas de cada línea existen, son apuntables y pertenecen a la empresa activa, en asientos de 1:1 y de N:M.
- **FR-007**: El sistema MUST admitir líneas repetidas de la misma cuenta dentro de un mismo asiento sin colapsarlas ni rechazarlas.
- **FR-008**: El sistema MUST conservar todas las líneas de cada asiento en la importación y exportación masiva (SPEC-005), sin truncar ni fusionar partidas.
- **FR-009**: La interfaz de entrada muy masiva MUST permitir añadir varias partidas por lado con fluidez por teclado (añadir fila, tabulación y atajos).
- **FR-010**: El flujo completo MUST cumplir las reglas inmutables de la constitución (partida doble estricta, inmutabilidad del diario, multi-tenancy, precisión decimal y pruebas obligatorias).

### Key Entities *(include if feature involves data)*

- **Cabecera de asiento**: Entidad del motor de asientos (SPEC-002) que agrupa las partidas; sin límite de líneas por lado.
- **Partida / apunte (línea)**: Cada línea pertenece a la cabecera e indica cuenta, Debe o Haber y detalle; un asiento contiene una o más líneas por lado.
- **Asiento rectificativo**: Asiento generado al anular un original multilínea, con sus líneas invertidas.
- **Grupo de importación**: Conjunto de líneas de un mismo asiento en los archivos de importación/exportación (SPEC-005).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de los asientos con más de una partida por lado (N:M) se registran correctamente, manteniendo Sum(Debe) == Sum(Haber).
- **SC-002**: El 100 % de los asientos con un lado vacío son rechazados con un mensaje claro y sin datos parciales.
- **SC-003**: El 100 % de las anulaciones de asientos multilínea generan el rectificativo con todas las líneas invertidas y balanceado.
- **SC-004**: El 100 % de los asientos multilínea exportados e importados conservan todas sus líneas y su balance (verificado por pruebas automáticas).
- **SC-005**: El contador puede introducir un asiento multilínea por teclado en menos de 30 segundos para hasta 10 partidas totales.

## Assumptions

- Esta feature refuerza y amplía SPEC-002 (motor de asientos): el soporte multilínea se asume como parte del mismo motor, no como un módulo separado.
- No existe límite de líneas por asiento en el dominio; los límites prácticos (rendimiento) se definirán en el diseño técnico.
- La agrupación de líneas por asiento en los archivos de importación/exportación se define en la plantilla de SPEC-005; esta feature garantiza que no se pierdan líneas.
- La interfaz de teclado se rige por la norma de entrada contable optimizada de la constitución (fila dinámica, tabulación y atajos).
- El aislamiento por empresa y los roles provienen de SPEC-003; la precisión decimal, de la norma de importes de la constitución.

## Dependencias

- SPEC-002 (motor de asientos), SPEC-005 (import/export multilínea).