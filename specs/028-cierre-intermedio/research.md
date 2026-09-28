# Research: Cierre Intermedio y Reapertura Controlada (SPEC-028)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Resoluciones de los unknowns del Technical Context y decisiones de diseño conforme a la constitución y al plan raíz.

## D1. Naturaleza del cierre intermedio: snapshot control vs. generación de asientos

- **Decision**: El cierre intermedio (mensual/trimestral) genera **únicamente un snapshot inmutable** (`BalanzaPeriodo` + `BalanzaPeriodoLinea`) con el balance de comprobación y el resultado provisional del periodo, **sin crear asientos en el diario** y sin mutar asientos existentes. Los asientos de cierre y regularización se generan **únicamente en el cierre anual completo** (US2). El resultado provisional se calcula en memoria sobre los asientos POSTED del periodo y se expone para informes.
- **Rationale**: Cumple el supuesto de la spec (Assumption: "Los cierres intermedios son informativos y de control; no generan asientos de cierre automáticos") y la constitución II (inmutabilidad); evita proliferar asientos de control que ensucien el diario; el snapshot sí queda registrado (AS1: "el balance queda registrado") y alimenta la exportación (SPEC-029) y el cálculo del IS intermedio (SPEC-023).
- **Alternatives considered**: Generar asientos `PROVISIONAL` en borrador para el cierre intermedio (rompe la distinción borrador/asentado, genera complejidad innecesaria); calcular on-the-fly sin persistir (incumple AS1, sin trazabilidad para auditoría/export). Se descartaron ambas.

## D2. Representación de periodos y bloqueo de contabilización

- **Decision**: Entidad `PeriodoCerrado` con clave natural `(empresa_id, ejercicio, tipo, periodo)` única. El tipo puede ser `MES` (periodo 1–12) o `TRIMESTRE` (periodo 1–4). Cerrar un trimestre bloquea el rango completo de fechas de ese trimestre sin cerrar los meses individuales; cerrar un mes bloquea solo ese mes. Bloquear un ejercicio (`ANUAL`) requiere que todos los periodos intermedios (meses o trimestres, según la configuración) estén cerrados. El bloqueo se implementa a nivel de servicio de creación de asientos (SPEC-002) con validación `fecha_asiento NOT IN (rango de periodos cerrados)` y como trigger DB que revisa `PeriodoCerrado` antes de permitir INSERT en `JournalEntryLine`.
- **Rationale**: Clave natural única evita duplicidades; trimestre envuelve meses sin crear celdas derivadas; el bloqueo a dos niveles (servicio + trigger) protege contra bypass accidental.
- **Alternatives considered**: Tabla de periodos tipo calendario (alrededor de 80 rows por empresa x 12 meses × N ejercicios, crece innecesariamente); bloqueo solo a nivel de servicio (no previene bypass directo a DB); se descartaron.

## D3. Balance de comprobación como snapshot inmutable

- **Decision**: El balance de comprobación del periodo se persiste en `BalanzaPeriodo` (cabecera) y `BalanzaPeriodoLinea` (líneas por cuenta) como snapshot inmutable: INSERT único, sin UPDATE/DELETE, con `total_debe == total_haber` validado al persistir y `sha256` del contenido del snapshot (para verificación futura). El snapshot se almacena en la misma transacción ACID que el registro `PeriodoCerrado` y el audit log.
- **Rationale**: Cumple AS1 ("el balance queda registrado"), provee trazabilidad auditada, alimenta SPEC-029 (export integral incluye cierres/informes) y permite comparativas entre cierres intermedios.
- **Alternatives considered**: Calcular on-the-fly sin persistir (sin trazabilidad); tabla mutable con UPDATE por recalculo (rompe la inmutabilidad del informe); ambas se descartaron.

## D4. Resultado provisional e IS intermedio (SPEC-023)

- **Decision**: El resultado del periodo se obtiene calculando la suma de las cuentas de gestión (grupos 6 y 7) en el rango del periodo sobre asientos POSTED. El **PyG provisional** se genera en memoria a partir de ese cálculo y se persiste como parte de la `BalanzaPeriodo` o como informe ad-hoc. Para el **IS provisional** (SPEC-023 FR-007): si el cierre del IS del periodo aún no se ha contabilizado, el sistema permite calcular una cifra provisional sin asentar; si el IS ya se ha contabilizado, la reapertura del periodo no reabre el IS (impacto parcial documentado en la solicitud de reapertura).
- **Rationale**: Cobre la necesidad de información fiscal periódica sin romper la regla de que el cierre anual es el que genera los asientos formales; coherente con SPEC-023 que prevé cálculos provisionales en cierres intermedios.
- **Alternatives considered**: Generar el asiento del IS directamente en el cierre intermedio (prematura, afecta a ejercicios en curso); no calcular nada intermedio (incumple la demanda de informes periódicos).

## D5. Cierre anual completo: regularización + cierre + apertura

- **Decision**: El cierre anual se ejecuta como un solo proceso atómico que: (1) valida que todos los periodos intermedios estén cerrados; (2) genera el asiento de regularización (cuentas de resultados grupos 6–7); (3) genera el asiento de cierre del ejercicio; (4) marca `is_closed = True` en el ejercicio; (5) invoca la apertura del siguiente ejercicio (SPEC-009). Todos los asientos se crean como POSTED (inmutables) en una sola transacción ACID; el `CierreEjercicio` queda registrado con `estado=completado`. El flujo es idempotente: reintentar el cierre de un ejercicio ya cerrado devuelve 409 sin generar duplicados.
- **Rationale**: Cumple SPEC-004 FR-008 (atomicidad del cierre), SPEC-009 (apertura), y la constitución (partida doble, inmutabilidad, numeración atómica).
- **Alternatives considered**: Cierre manual paso a paso sin atomicidad (riesgo de estado parcial); cierre sin requerir periodos intermedios cerrados (incumple la integridad del ciclo).

## D6. Reapertura controlada: flujo completo

- **Decision**: La reapertura sigue un flujo de estados: `pendiente → aprobada → reabierta → cerrada (ajuste completado)` (o `→ rechazada`). Requisitos: (1) justificación obligatoria (FR-006); (2) permiso de rol autorizado (ADMIN/ACCOUNTANT, SPEC-015); (3) un solo periodo con solicitud activa a la vez (uno a la vez); (4) rechazo automático si el ejercicio está legalizado/formulado (SPEC-010) o si el IS fue liquidado (SPEC-023) sin justificación adicional. Al aprobarse, el periodo pasa a `estado=reabierto_ajuste` y se desbloquea temporalmente; al publicarse el asiento de rectificación y confirmar el ajuste, se re-cierra automáticamente (`estado=cerrado_ajustado`) y se incrementa `n_reaperturas`. La solicitud de reapertura tiene número correlativo por `(empresa_id, ejercicio)`.
- **Rationale**: Cumple FR-003/FR-004/FR-005/FR-006; asegura trazabilidad total; la restricción "uno a la vez" evita abusos; los bloqueos de ejercicio legalizado y IS protegen la integridad legal/fiscal.
- **Alternatives considered**: Reapertura inmediata sin flujo de aprobación (rompe el control documentado); reapertura múltiple simultánea (dificulta la consistencia); ambas contrarias a la spec.

## D7. Asiento de rectificación en la reapertura

- **Decision**: La reapertura **no genera automáticamente** el asiento de rectificación: el usuario crea el asiento `ADJUSTMENT` o `REVERSAL` a través del motor de asientos (SPEC-002) durante el periodo reabierto, validando `tipo` y `fecha_asiento` dentro del rango reabierto. Al confirmar el cierre de la reapertura (`POST /reaperturas/{id}/rectificar`), el sistema vincula el asiento a `SolicitudReapertura.asiento_rectificacion_id` y re-cierra el periodo. El asiento de rectificación debe estar balanceado (Debe==Haber) y su `reverses_id` apunta al asiento original que se corrige. El asiento original **nunca se modifica** (constitución II).
- **Rationale**: Mantiene la separación de responsabilidades: el motor de asientos crea y valida el asiento; el servicio de reapertura controla el ciclo de vida del periodo. La verificación del balance se hace en SPEC-002 (validate near persistence) y se re-verifica al enlazar.
- **Alternatives considered**: Generar el asiento automáticamente dentro de la reapertura (mezcla lógica de negocio); el usuario crea el asiento sin verificar tipo/fecha (riesgo de asiento fuera de rango).

## D8. Ampliación del tipo de asiento (JournalEntry.tipo)

- **Decision**: Añadir al `ENUM tipo` del modelo `JournalEntry` los valores `REGULARIZACION`, `CIERRE`, `APERTURA`, `ADJUSTMENT` y `REVERSAL` (si no existían en SPEC-002). Añadir campo `reverses_id UUID NULL` FK self-referencing que enlaza el asiento de rectificación con el original. Se añade `cierre_id UUID NULL` FK → `CierreEjercicio.id` para trazabilidad del cierre anual. La migración se aplica de forma backward-compatible (nuevos valores en ENUM, campos nullable).
- **Rationale**: Permite clasificar y trazar los asientos de cierre y de rectificación sin romper asientos existentes; `reverses_id` es la base de la cadena de inmutabilidad y de la auditoría de correcciones.
- **Alternatives considered**: Usar una tabla de vínculos separada (más compleja, menos coherente con el modelo existente); no ampliar tipos y usar el campo estado (pierde semántica).

## D9. Bloqueo cross-módulo de periodos cerrados

- **Decision**: La validación de periodo cerrado se integra en el servicio de creación de asientos de SPEC-002 (`backend/src/services/acct/asiento.py`) como una función reusable `validar_periodo_abierto(fecha, empresa_id)` que consulta `PeriodoCerrado` en la misma transacción antes de INSERT. Si la fecha cae en un periodo cerrado, se rechaza con HTTP 409 `periodo_cerrado` (consistente con el precedente de SPEC-020 que usa 409 para ejercicios cerrados). También se añade un trigger DB `chk_journal_entry_fecha_abierta` que verifica antes de INSERT en `JournalEntry`/`JournalEntryLine`. Los módulos de facturación (SPEC-007), cobros/pagos (SPEC-011) y amortizaciones (SPEC-014) heredan el bloqueo vía el mismo servicio de asientos.
- **Rationale**: Doble protección (servicio + trigger) contra bypass; coherente con SPEC-004 FR-007; el trigger protege también contra inserciones directas a nivel de migración/scripts.
- **Alternatives considered**: Bloqueo solo a nivel de UI (no previene bypass); trigger DB sin servicio (pierde la capacidad de devolver mensajes de error específicos); ambas se descartaron.

## D10. Stack, estructura y transacciones

- **Decision**: Servios bajo `services/closing/` con `async with async_session.begin()`; snapshot de balanza persistido en la misma transacción que `PeriodoCerrado` y audit log; `CierreEjercicio` y `SolicitudReapertura` también se persisten con audit ACID. El frontend Next.js consume los endpoints de cierres y muestra el formulario de reapertura con validación client-side (informativa, nunca reemplaza backend). Los tests de balance usan `Decimal` para todas las comparaciones de importes.
- **Rationale**: Cumple la constitución (transacciones atómicas, auditoría, precisiones, pruebas); coherente con el patrón del módulo `treasury/` de SPEC-020.
- **Alternatives considered**: Generar el cierre en un worker asíncrono (complica la UX para periodos; no aporta para el volumen esperado < 50 k asientos).
