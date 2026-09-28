# Data Model: Cierre Intermedio y Reapertura Controlada (SPEC-028)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Reglas transversales (constitución):
- Toda tabla incluye `empresa_id BIGINT NOT NULL` (referencia SPEC-003) en PK/índices y filtros; se deriva de sesión, nunca del request.
- Importes en `NUMERIC(18,4)`/`Decimal`; prohibido `float`.
- Cada escritura se persiste con su registro de auditoría en la misma transacción ACID.
- `BalanzaPeriodo` y sus líneas son inmutables (INSERT único, sin UPDATE/DELETE).

## PeriodoCerrado

Registro del estado de cierre de un periodo intermedio o anual dentro de un ejercicio.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | parte de la clave única (empresa_id, ejercicio, tipo, periodo) |
| ejercicio | INT | ejercicio contable (SPEC-004) |
| tipo | ENUM | `MES` (1–12) / `TRIMESTRE` (1–4) |
| periodo | INT | número del periodo dentro del ejercicio (1..12 o 1..4) |
| fecha_ini | DATE | fecha de inicio del periodo |
| fecha_fin | DATE | fecha de fin del periodo |
| estado | ENUM | `abierto`, `cerrado`, `reabierto_ajuste`, `cerrado_ajustado` |
| cerrado_por | UUID | usuario que ejecutó el cierre |
| cerrado_at | TIMESTAMPTZ | momento del cierre (UTC) |
| balanza_id | UUID NULL | FK → BalanzaPeriodo.id (snapshot del balance) |
| n_reaperturas | INT | contador de reaperturas del periodo (default 0) |
| created_at | TIMESTAMPTZ | |

**Validaciones**:
- Un periodo solo admite un registro por `(empresa_id, ejercicio, tipo, periodo)` (clave única).
- El rango `fecha_ini..fecha_fin` debe corresponder al mes o trimestre dentro del ejercicio; se deriva del calendario.
- Cerrar un `TRIMESTRE` solo es válido si los meses que lo componen no están en conflicto (un mes cerrado dentro de un trimestre abierto se fusiona al cerrar el trimestre: el trimestre ya lo bloquea).
- Al cerrar un `MES` no se requiere cerrar el resto del trimestre.

**Transiciones de estado**: `abierto → cerrado` (cierre intermedio, snapshot de balanza) | `cerrado → reabierto_ajuste` (reapertura aprobada) | `reabierto_ajuste → cerrado_ajustado` (ajuste completado) | `cerrado_ajustado` puede volver a reabrirse (con nueva solicitud y contador++).

## BalanzaPeriodo

Snapshot inmutable del balance de comprobación del periodo generado al cerrar un periodo intermedio.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| periodo_id | UUID FK → PeriodoCerrado | único (1 balanza por cierre) |
| ejercicio | INT | |
| tipo | ENUM | `MES` / `TRIMESTRE` |
| fecha_ini / fecha_fin | DATE | rango del periodo |
| fecha_generacion | TIMESTAMPTZ | (UTC) |
| generado_por | UUID | |
| n_lineas | INT | número de líneas persistentes |
| total_debe | NUMERIC(18,4) | suma del Debe de las líneas |
| total_haber | NUMERIC(18,4) | suma del Haber de las líneas |
| sha256 | CHAR(64) | huella del contenido del snapshot |

**Validaciones**: al persistir, `total_debe` MUST ser exactamente igual a `total_haber` (partida doble estricta); si no, la transacción se aborta y el cierre falla. El snapshot es inmutable.

## BalanzaPeriodoLinea

Línea por cuenta del snapshot del periodo.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| balanza_id | UUID FK → BalanzaPeriodo | |
| cuenta_id | UUID FK → SPEC-001 CuentaContable | cuenta de la empresa activa |
| codigo | VARCHAR(20) | código de la cuenta (snapshot del momento) |
| nombre | VARCHAR(150) | nombre de la cuenta (snapshot del momento) |
| nivel | INT | nivel del plan (1–5) |
| debe | NUMERIC(18,4) | suma de debe en el periodo |
| haber | NUMERIC(18,4) | suma de haber en el periodo |
| saldo | NUMERIC(18,4) | debe - haber |

**Validaciones**: `saldo = debe - haber`; la suma de línea `debe` == `balanza.total_debe`; idem haber. FK compuesta con `empresa_id`.

## CierreEjercicio

Registro del cierre anual completo de un ejercicio (integración SPEC-004/SPEC-009).

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| ejercicio | INT | |
| estado | ENUM | `completado`, `reapertura_pendiente` |
| fecha_cierre | DATE | |
| resultado_ejercicio | NUMERIC(18,4) | resultado calculado en la regularización |
| asiento_regularizacion_id | UUID FK → JournalEntry | tipo `REGULARIZACION` |
| asiento_cierre_id | UUID FK → JournalEntry | tipo `CIERRE` |
| asiento_apertura_id | UUID FK NULL → JournalEntry | tipo `APERTURA` (SPEC-009) |
| cerrado_por | UUID | |
| cerrado_at | TIMESTAMPTZ | |

**Validaciones**: un único cierre por `(empresa_id, ejercicio)` (clave única); el cierre solo se ejecuta con todos los periodos intermedios del ejercicio `cerrado` (o reaperturas cerradas); idempotencia: reintento devuelve 409.

**Transición**: `completado → reapertura_pendiente` cuando una `SolicitudReapertura` de tipo `ANUAL` (ejercicio completo) es aprobada (requiere condiciones legales y de SPEC-010/023 superadas).

## SolicitudReapertura

Solicitud de reapertura de un periodo o ejercicio cerrado con trazabilidad completa.

| Campo | Tipo | Reglas |
|-------|------|--------|
| id | UUID PK | |
| empresa_id | BIGINT | |
| ejercicio | INT | |
| numero_solicitud | BIGINT | correlativo por (empresa_id, ejercicio), asignado atómicamente |
| periodo_id | UUID FK → PeriodoCerrado (nullable) | si la reapertura es de un periodo intermedio |
| tipo_periodo | ENUM | `MES` / `TRIMESTRE` / `ANUAL` |
| motivo | TEXT | justificación obligatoria (FR-006) |
| estado | ENUM | `pendiente`, `aprobada`, `reabierta`, `cerrada`, `rechazada` |
| usuario_solicitante | UUID | |
| fecha_solicitud | TIMESTAMPTZ | |
| aprobada_por | UUID NULL | |
| fecha_aprobacion | TIMESTAMPTZ NULL | |
| asiento_rectificacion_id | UUID FK NULL → JournalEntry | tipo `ADJUSTMENT` / `REVERSAL` |
| fecha_cierre_efectivo | TIMESTAMPTZ NULL | momento del re-cierre tras el ajuste |
| nota_impacto | TEXT NULL | impacto parcial documentado (ej. IS de SPEC-023) |

**Validaciones**:
- `motivo` MUST ser no vacío (rechazo 422 si falta).
- Una sola solicitud activa por periodo: no puede existir otra solicitud con estado `pendiente`/`aprobada`/`reabierta` para el mismo `periodo_id` (uno a la vez).
- Se rechaza automáticamente si el ejercicio está legalizado/formulado (SPEC-010) o si el IS (SPEC-023) ya está liquidado sin nota de impacto.
- La asignación de `numero_solicitud` es atómica dentro de la misma transacción (constitución IV).

**Transiciones de estado**:
```
pendiente → aprobada      (rol autorizado aprueba)
pendiente → rechazada     (rol autorizado rechaza)
aprobada  → reabierta     (se ejecuta la reapertura: desbloquea periodo)
reabierta → cerrada       (asiento de rectificación enlazado + re-cierre)
```

## JournalEntry / JournalEntryLine (ampliación SPEC-002)

Ampliación del motor de asientos (SPEC-002), no reemplazo.

| Campo | Tipo | Reglas |
|-------|------|--------|
| tipo | ENUM (ampliado) | añade `REGULARIZACION`, `CIERRE`, `APERTURA`, `ADJUSTMENT`, `REVERSAL` |
| reverses_id | UUID NULL | FK self-referencing → JournalEntry.id (asiento original corregido) |
| cierre_id | UUID NULL | FK → CierreEjercicio.id (trazabilidad del cierre anual) |

**Reglas inmutables heredadas** (constitución II):
- Los asientos POSTED (y los de cierre, tipo CIERRE/REGULARIZACION/APERTURA) son inmutables: UPDATE/DELETE prohibidos vía trigger DB.
- Un asiento `REVERSAL`/`ADJUSTMENT` nunca modifica el original; el `reverses_id` apunta a él.

## Resumen de relaciones

```
PeriodoCerrado 1 ── 0..1 BalanzaPeriodo
BalanzaPeriodo 1 ── n BalanzaPeriodoLinea
CierreEjercicio 1 ── 0..1 asiento_regularizacion (JournalEntry tipo REGULARIZACION)
CierreEjercicio 1 ── 0..1 asiento_cierre (JournalEntry tipo CIERRE)
CierreEjercicio 1 ── 0..1 asiento_apertura (JournalEntry tipo APERTURA)
JournalEntry 1 ── 0..1 reverses_id → JournalEntry (cadena de inmutabilidad)
PeriodoCerrado 1 ── 0..n SolicitudReapertura (solo 1 activa)
SolicitudReapertura 1 ── 0..1 asiento_rectificacion (JournalEntry ADJUSTMENT/REVERSAL)
Ejercicio (SPEC-004) 1 ── n PeriodoCerrado
Empresa (SPEC-003) 1 ── n PeriodoCerrado / BalanzaPeriodo / CierreEjercicio / SolicitudReapertura
```