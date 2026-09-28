# Data Model: Gestión ONG (Subvenciones, Libros Oficiales y Caja) (SPEC-019)

**Branch**: `019-gestion-ong-libros-caja` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

## Key Entities + FRs

- **Subvencion**: FR-002, FR-008 (control de gasto), FR-001.
- **GastoImputado**: FR-003, FR-001.
- **LibroOficial**: FR-005, FR-001.
- **Legalizacion**: FR-006, FR-007, FR-001.
- **Caja** (+ 570) y **Arqueo**: FR-008, FR-009, FR-001.

Cada entidad incluye `empresa_id` en PK/índices (constitución III). Importes siempre `NUMERIC(18,4)`/`Decimal` (FR-010).

## Dependencias

- **SPEC-001** (plan de cuentas): cuentas de gasto/ingreso y subcuenta 570 para cajas; validación de cuenta `activa`.
- **SPEC-002** (motor de asientos): los movimientos de caja y los ajustes de arqueo son asientos reales (balance, numeración, auditoría).
- **SPEC-004** (ejercicios): los libros/legalización exigen ejercicio cerrado; el refuerzo de bloqueo de FR-007.
- **SPEC-006** (multilínea): las líneas de asiento son la base de la imputación de gastos (nivel de línea).
- **SPEC-017** (centros de coste, opcional): vínculo opcional de centros con subvenciones; no bloquea esta feature.
- **SPEC-015** (permisos): matriz de roles sobre subvenciones, libros, legalización y caja.

## Tablas

### `subvencion`

| Campo | Tipo | Reglas |
|---|---|---|
| `empresa_id` | BIGINT / UUID | PK compuesta; FK empresa; derivado solo de sesión |
| `id` | BIGINT | PK compuesta |
| `entidad_concedente` | VARCHAR(120) | Obligatorio |
| `programa` | VARCHAR(120) | Obligatorio |
| `referencia` | VARCHAR(40) NULL | Nº de expediente/convocatoria |
| `importe_concedido` | NUMERIC(18,4) | > 0; `Decimal` |
| `ejercicio` | SMALLINT | Ejercicio de la subvención |
| `estado` | ENUM(`concedida`, `en_curso`, `justificada`, `reintegrada`) | Transiciones D8; `justificada→reintegrada` exige asiento rectificativo |
| `partidas` | JSONB NULL | Desglose de partidas del programa (opcional, decisión D10) |
| `observaciones` | TEXT NULL | |
| `created_at` / `updated_at` | TIMESTAMPTZ | Auditoría |

Transiciones de estado: `concedida → en_curso` → `justificada` (gastado ≥ concedido o decisión responsable) → `reintegrada` (con `ADJUSTMENT` enlazado para el reintegro). Sin retrocesos excepto corrección administrativa documentada.

### `gasto_imputado`

| Campo | Tipo | Reglas |
|---|---|---|
| `empresa_id` | BIGINT / UUID | PK compuesta; FK empresa |
| `id` | BIGINT | PK compuesta |
| `subvencion_id` | BIGINT | FK compuesta a `subvencion` (misma empresa) |
| `asiento_id` | BIGINT | FK a `JournalEntry` (misma empresa) |
| `linea_id` | BIGINT | FK a `JournalEntryLine` (misma empresa) — apunte de gasto concreto (D2) |
| `importe_asignado` | NUMERIC(18,4) | > 0; ≤ saldo restante de la línea; `Decimal` |
| `partida` | VARCHAR(80) NULL | Partida del programa (si aplica) |
| `created_at` | TIMESTAMPTZ | Momento de la imputación |

Reglas (validación en la misma transacción ACID, D7):
- Lo ya imputado a la línea (suma de `gasto_imputado`) + nuevo `importe_asignado` ≤ importe total de la línea (evita doble imputación del mismo importe).
- Acumulado de la subvención (incluido el nuevo) ≤ `importe_concedido` de las partidas vigentes (rechazo de exceso, FR-003) con `SELECT ... FOR UPDATE` sobre la subvención.
- No modifica la línea ni el asiento (constitución II); es una asignación externa al diario.

### `libro_oficial`

| Campo | Tipo | Reglas |
|---|---|---|
| `empresa_id` | BIGINT / UUID | PK compuesta; FK empresa |
| `id` | BIGINT | PK compuesta |
| `ejercicio` | SMALLINT | Ejercicio cerrado (SPEC-004) |
| `tipo` | ENUM(`diario`, `mayor`, `cuentas_anuales`) | |
| `periodo_desde` / `periodo_hasta` | DATE | Rango cubierto |
| `contenido_pdf` | BYTEA | PDF generado (D3); no editable |
| `sha256` | CHAR(64) | Huella SHA-256 del contenido canónico |
| `size_bytes` | BIGINT | Tamaño |
| `generado_por` | BIGINT | Actor |
| `created_at` | TIMESTAMPTZ | |

Reglas:
- Solo para ejercicios cerrados (FR-005); el PDF refleja fielmente el diario/mayor inmutable (SC-002).
- `generado_por`/`created_at` y audit log en la misma transacción que la generación.

### `legalizacion`

| Campo | Tipo | Reglas |
|---|---|---|
| `empresa_id` | BIGINT / UUID | PK compuesta; FK empresa |
| `id` | BIGINT | PK compuesta |
| `ejercicio` | SMALLINT | Solo ejercicios cerrados (FR-006) |
| `rango_asientos_desde` / `rango_asientos_hasta` | BIGINT | Nº correlativos primero/último del ejercicio (motor SPEC-002) |
| `total_asientos` | INT | Cantidad legalizada |
| `huella` | CHAR(64) | SHA-256 del contenido canónico (PDFs + metadatos, contrato `legalizacion.md`) |
| `fichero` | BYTEA | Contenido del fichero de legalización |
| `fecha_emision` | TIMESTAMPTZ | |
| `fecha_legalizacion` | DATE | Fecha formal (trámite externo; Assumption) |
| `valido` | BOOLEAN | true = legalización vigente; false si una re-emisión distinta fuese rechazada |
| `motivo_reemision` | TEXT NULL | Solo si re-emitida |
| `created_at` | TIMESTAMPTZ | Última emisión |

Reglas (D4):
- Re-emisión del mismo ejercicio permitida únicamente si la huella recalculada == `huella` original; si difiere → rechazo 409.
- Un ejercicio legalizado (`valido = true`) refuerza el bloqueo de SPEC-004: no admite asientos posteriores con fecha dentro del ejercicio (FR-007; refuerzo en DB/servicios del motor).

### `caja`

| Campo | Tipo | Reglas |
|---|---|---|
| `empresa_id` | BIGINT / UUID | PK compuesta; FK empresa |
| `id` | BIGINT | PK compuesta |
| `nombre` | VARCHAR(80) | Obligatorio; único por empresa |
| `cuenta_570_id` | BIGINT | Subcuenta **570 real** del plan de la empresa (SPEC-001); 1 caja = 1 subcuenta 570 (D5); única por caja |
| `tipo` | ENUM(`caja`, `caja_chica`) | |
| `estado` | ENUM(`activa`, `inactiva`) | |
| `created_at` / `updated_at` | TIMESTAMPTZ | |

### `movimiento_caja` (traza derivada del diario)

| Campo | Tipo | Reglas |
|---|---|---|
| `empresa_id` | BIGINT / UUID | PK compuesta; índice para la consulta |
| `id` | BIGINT | PK compuesta (identidad de traza) |
| `caja_id` | BIGINT | FK compuesta a `caja` (misma empresa) |
| `asiento_id` / `linea_id` | BIGINT | FK al asiento/línea que mueve la 570 (motor SPEC-002) |
| `tipo` | ENUM(`entrada`, `salida`) | Derivado de Debe/Haber de la línea 570 |
| `importe` | NUMERIC(18,4) | `Decimal`; derivado de la línea (sin duplicar contabilidad) |
| `fecha` | DATE | Fecha del asiento |
| `created_at` | TIMESTAMPTZ | |

Reglas:
- No duplica importes: es una **vista/índice de las líneas del diario** de la 570 de la caja (D5). Se materializa en la transacción del asiento del motor que afecta a una 570 asignada.
- Sin UPDATE/DELETE (deriva del diario inmutable).

### `arqueo`

| Campo | Tipo | Reglas |
|---|---|---|
| `empresa_id` | BIGINT / UUID | PK compuesta; FK empresa |
| `id` | BIGINT | PK compuesta |
| `caja_id` | BIGINT | FK compuesta a `caja` (misma empresa) |
| `fecha` | DATE | Fecha del arqueo |
| `saldo_libros` | NUMERIC(18,4) | Suma de líneas 570 de la caja hasta `fecha` (precisión exacta) |
| `efectivo_contado` | NUMERIC(18,4) | Efectivo físico anotado |
| `diferencia` | NUMERIC(18,4) | `efectivo_contado - saldo_libros` (puede ser negativa) |
| `estado` | ENUM(`cuadra`, `con_diferencia`) | `con_diferencia` si |diferencia| > 0 |
| `decision` | ENUM(`pendiente`, `aprobada`, `archivada`) NULL | Tras decisión del responsable |
| `asiento_ajuste_id` | BIGINT NULL | Asiento de ajuste enlazado que cuadra 570 con el efectivo (D6) |
| `archivado` | BOOLEAN | true = archivado sin asiento (diferencia pendiente visible) |
| `detalle_diferencia` | TEXT NULL | Justificación opcional |
| `created_at` | TIMESTAMPTZ | |

Reglas (D6):
- `cuadra`: diferencia == 0 → se aprueba automáticamente, sin asiento.
- `con_diferencia`: decisión `aprobada` exige `asiento_ajuste_id` no nulo (asiento del motor, balanceado, que deja 570 == efectivo tras el ajuste); si la decisión es `archivada`, `asiento_ajuste_id = NULL` y `decision = archivada`, quedando la diferencia pendiente visible.
- Si el ajuste se registra después de archivar, pasa a `aprobada` y se descuenta del archivo.

## Resumen de relaciones

```text
empresa (SPEC-000) 1─N subvencion 1─N gasto_imputado N─1 journal_entry_line N─1 journal_entry (SPEC-002/006)
                          │ 1─N gasto_imputado (partida, mismo asiento/línea)
empresa 1─N libro_oficial (ejercicio, tipo)
empresa 1─N legalizacion (ejercicio cerrado; huella de los PDF/meta)
empresa 1─N caja 1─N movimiento_caja N─1 asiento 570 (motor) ;  caja 1─N arqueo → asiento_ajuste (opcional)
```

- Un gasto puede repartirse en importes parciales entre varias subvenciones/partidas; una línea no supera su importe total (D7).
- Una caja usa una única subcuenta 570; los movimientos son asientos reales (no paralelos).
- Un arqueo con diferencia aprobada se enlaza a un asiento de ajuste; uno archivado no, y queda pendiente visible.