# Research: Cuentas Anuales (SPEC-010)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Resoluciones de los unknowns del Technical Context y decisiones de diseño conforme a la constitución y al plan raíz.

## D1. Estructura del balance y PyG a partir del plan de cuentas

- **Decision**: La estructura de balance (masas: activo corriente/no corriente, pasivo, patrimonio neto) y de PyG (grupos 6 y 7) se deriva de las agrupaciones del plan de cuentas (SPEC-001) con configuración por empresa: cada cuenta se asigna a una masa/agrupación de nivel 1-3. Si una cuenta no tiene agrupación asignada, se clasifica en una agrupación "Otros" y se avisa.
- **Rationale**: Reutiliza el plan de cuentas existente y respeta la configuración por empresa (asumción del spec).
- **Alternatives considered**: Tablas fijas de agregación (rigidez entre empresas); clasificación automática por prefijo de cuenta (servicial pero frágil ante planes no estándar).

## D2. Cálculo de saldos para el balance

- **Decision**: Los saldos se calculan por agregación de asientos `POSTED` del ejercicio (SPEC-001/002), excluyendo asientos de regularización/cierre para el balance "de gestión" provisional, y confrontando el balance oficial cuando el ejercicio está cerrado. Activo = cuenta con saldo deudor; pasivo/patrimonio = saldo acreedor. El cuadre Activo == Pasivo + Patrimonio se verifica con aritmética `Decimal` exacta.
- **Rationale**: El balance surge del diario; el cuadre es una propiedad emergente de asientos balanceados. La verificación en backend es obligatoria (constitución I).
- **Alternatives considered**: Balance "predefinido" a partir de campos de saldo (se desincroniza del diario); solo UI valida cuadre (prohibido).

## D3. Resultado de la PyG y coincidencia con el cierre

- **Decision**: La PyG agrega ingresos (grupo 7) y gastos (grupo 6) del ejercicio. El resultado = Ingresos - Gastos. Se compara con el asiento de regularización/cierre (SPEC-004): si difieren, se advierte con `descuadre_cierre` y solo se permite la formulación oficial si coinciden.
- **Rationale**: FR-006 del spec exige que el resultado coincida con la regularización. La advertencia evita formular resultados inconsistentes.
- **Alternatives considered**: Confiar solo en la agregación (puede diferir del cierre al no estar regularizado).

## D4. Estado de Flujos de Efectivo (EFE)

- **Decision**: El EFE se construye a partir de los movimientos de saldos de las cuentas de tesorería (grupo 5, típicamente 570/572) y de la clasificación por actividad (operativa, inversión, financiación) derivada del grupo de la contrapartida, con reasignación manual permisible antes de formular. Cuadre: Saldo inicial + Cobros - Pagos = Saldo final y variación == variación de tesorería del Balance.
- **Rationale**: FR-008; el enfoque "directo" desde movimientos de tesorería es el más trazable y evita construir el EFE "indirecto" desde resultados ajustados. La reasignación manual cubre el edge case de movimientos no clasificados.
- **Alternatives considered**: Método indirecto (más complejo y dependiente del resultado); solo automatizado sin validación de cuadre (puede producir descuadres silenciosos).

## D5. Formulación oficial e inmutabilidad

- **Decision**: La formulación oficial requiere ejercicio `cerrado`. Al formular, se genera un documento `FormulacionCuentasAnuales` (id, empresa, ejercicio, fecha UTC, usuario, hash del contenido) que congela el juego de informes. Una reformulación solo se permite previa anulación explícita con motivo, permiso de administrador y trazabilidad; la formulación original permanece en histórico.
- **Rationale**: FR-004/FR-005. La inmutabilidad del documento se alinea con constitución II (los asientos origen tampoco cambian en un ejercicio cerrado).
- **Alternatives considered**: Editar una formulación (rompe inmutabilidad); re-formular sin registro (pierde trazabilidad).

## D6. Comparativa con ejercicio anterior

- **Decision**: El balance y la PyG incluyen columnas comparativas con el ejercicio anterior (T-04) cuando el ejercicio anterior existe y ya tiene informe formulado o provisional. Es opcional y configurable por empresa.
- **Rationale**: T-04 del spec; aporta valor de análisis sin añadir obligaciones legales.
- **Alternatives considered**: No comparativa (se pierde utilidad analítica).

## D7. Propagación de aislamiento multi-tenant

- **Decision**: Todas las consultas de saldos, agregaciones y formulaciones filtran por `empresa_id` derivado de sesión. Las pruebas de integración demuestran que la empresa A no ve cuentas ni informes de la empresa B.
- **Rationale**: Constitución III.
- **Alternatives considered**: empresa_id en body (prohibido por constitución).

## D8. Precisión decimal y redondeo

- **Decision**: Todos los totales y subtotales se calculan en `Decimal` con contexto de alta precisión y se expone con 4 decimales. Se implementan tests de redondeo para masas binarias (activación de 0,00005).

- **Rationale**: SC-005; prohíbe errores de coma flotante.
- **Alternatives considered**: Redondeos intermedios (descuadran sumas).

## D9. Salidas e integración con libros oficiales

- **Decision**: Los informes se exponen como fichas de cuentas anuales (JSON para API, HTML/PDF imprimible) y se enlazan con los libros oficiales (SPEC-019). El permiso de formulación se controla por rol (SPEC-015).
- **Rationale**: T-06 y dependencia de SPEC-019; la exportación queda delegada a SPEC-029 (export integral).
- **Alternatives considered**: Exportación PDF propia en esta feature (ampliación de alcance; se difiere).