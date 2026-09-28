# Contracto: Fichero de Legalización (SPEC-019)

**Branch**: `019-gestion-ong-libros-caja` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

Formato del fichero de legalización emitido por `POST /api/v1/legalizaciones` (FR-006). Certifica la integridad de los libros de un ejercicio cerrado (empresa, ejercicio, rango de asientos y **huella de verificación**). El trámite formal externo queda fuera (Assumption).

## 1. Contenido del fichero

Es un documento de **texto plano fijo** (encoding UTF-8, saltos de línea `\n`) con encabezado `LEGALIZACION V1`. Los importes/rangos se serializan sin reordenar.

```text
LEGALIZACION V1
EMPRESA:<razon_social>
NIF:<nif>
EJERCICIO:<aaaa>
RANGO_ASIENTOS_DESDE:<n>
RANGO_ASIENTOS_HASTA:<n>
TOTAL_ASIENTOS:<m>
FECHA_EMISION:<YYYY-MM-DDTHH:MM:SSZ>
FECHA_LEGALIZACION:<YYYY-MM-DD>
HUELLA:<sha256 hex de 64 caracteres>
HUELLA_ALGORITMO:SHA-256
```

| Campo | Regla |
|---|---|
| `EMPRESA` / `NIF` | Razón social y NIF de la empresa activa |
| `EJERCICIO` | El ejercicio legalizado (cerrado, SPEC-004) |
| `RANGO_ASIENTOS_DESDE/HASTA` | Números correlativos primero y último del diario del ejercicio (motor SPEC-002) |
| `TOTAL_ASIENTOS` | `RANGO_ASIENTOS_HASTA - RANGO_ASIENTOS_DESDE + 1` (correlativos sin saltos) |
| `FECHA_EMISION` | Momento de emisión (UTC) |
| `FECHA_LEGALIZACION` | Fecha formal (si aportada) |
| `HUELLA` | SHA-256 del contenido canónico (ver §2) |

## 2. Cálculo de la huella

La huella se calcula sobre el **contenido canónico** (no sobre el binario del PDF), garantizando estabilidad entre re-emisiones:

```text
canon = empresa_id | ejercicio | rango_desde | rango_hasta |
        para cada asiento del ejercicio (nº, fecha, y líneas con cuenta, debe, haber en 4 decimales)
huella = SHA-256(canon)   # hex minúscula, 64 caracteres
```

- La misma fuente (diario inmutable) produce siempre la misma huella (D4).
- **Re-emisión del mismo ejercicio**: solo si la huella recalculada == la `huella` de la legalización vigente; si difiere → **409** y no se emite (clarificación integrada).
- Además, `libro_oficial.sha256` de cada PDF debe coincidir con lo referenciado por la legalización; si el PDF cambió entre emisiones, la huella canónica cambia y se rechaza.

## 3. Estado del ejercicio y bloqueo (FR-007)

- La emisión exige ejercicio `cerrado` (SPEC-004).
- Una legalización vigente (`valido = true`) enlaza el refuerzo del bloqueo de SPEC-004: no admite asientos posteriores con fecha dentro del ejercicio (verificado en la generación de legalización y en los servicios del motor).

## 4. Validaciones del contrato (tests de contrato)

- `backend/tests/contract/test_legalizacion_formato.py`: genera para un ejercicio de fixtures y verifica (a) formato exacto de los 10 campos, (b) `TOTAL_ASIENTOS == nº asientos del ejercicio`, (c) `HUELLA` recalculable 64 hex en minúscula, (d) re-emisión con el mismo contenido → 201 y huella idéntica, (e) re-emisión habiendo cambiado el contenido (fixture alterada) → 409.
- `backend/tests/contract/test_legalizacion_ejercicios.py`: ejercicio abierto → 409; un asiento añadido con fecha dentro del ejercicio legalizado → rechazo por el bloqueo (FR-007).