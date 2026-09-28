# Quickstart: Gestión ONG (Subvenciones, Libros Oficiales y Caja) (SPEC-019)

**Branch**: `019-gestion-ong-libros-caja` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

Validación ejecutable de los escenarios clave. No incluye código de implementación; referencia `contracts/api-contracts.md`, `contracts/libros-pdf.md`, `contracts/legalizacion.md` y `data-model.md`.

## Prerrequisitos

- Repositorio ContabilidadV1 con backend (FastAPI + asyncpg) y frontend (Next.js) del plan raíz.
- PostgreSQL 16+ con migraciones de `ngo/` aplicadas.
- Motor de asientos multilínea (SPEC-002/006), plan de cuentas (SPEC-001) y ejercicios (SPEC-004) operativos.
- Un ejercicio con asientos `POSTED` y un ejercicio cerrado disponibles para la empresa de prueba.
- pytest instalado en el entorno del backend.

## Escenario 1 — Subvención y justificación de gastos (US1)

### Pasos
1. AUTENTICARSE como responsable de **Empresa A**; cabecera de empresa activa = A.
2. `POST /api/v1/subvenciones` con `{entidad_concedente, programa, importe_concedido: "5000.0000", ejercicio}` (201).
3. Tomar una línea de gasto (Debe) de un asiento `POSTED` de A y `POST /api/v1/subvenciones/{id}/gastos` con `importe_asignado "2000.0000"` (201).
4. Imputar otros `3500.0000` → **409** excede el disponible (2000+3500 > 5000).
5. `GET /api/v1/informes/subvenciones/{id}/justificacion` → concedido 5000, gastado 2000, pendiente 3000.

### Verificación
- Límite de disponible respetado en backend (no UI); informe con precisión `Decimal`.
- Imputar una línea de gasto de **Empresa B** → 404 (aislamiento).

```bash
curl -X POST "$BASE/api/v1/subvenciones" -H "Authorization: Bearer $TOKEN" -H "X-Empresa-Activa: A" \
  -H "Content-Type: application/json" \
  -d '{"entidad_concedente":"Fundación X","programa":"Programa Y","importe_concedido":"5000.0000","ejercicio":2026}'

pytest backend/tests/integration/test_subvencion_justificacion.py -q
pytest backend/tests/integration/test_subvencion_tenant.py -q
```

Resultado esperado: 201 + 201 + 409 + informe correcto; tests verdes (aislamiento incluido).

## Escenario 2 — División de línea entre subvenciones y doble imputación (US1)

### Pasos
1. Crear una segunda subvención en A.
2. Imputar la misma línea con `importe_asignado` parcial a la segunda subvención (suma de asignaciones ≤ importe de la línea) → 201.
3. Re-imputar el mismo importe exacto a la primera → **409** (doble imputación del mismo importe, suma de línea excedida).

### Verificación
- Suma de `gasto_imputado` por línea ≤ importe de la línea.

```bash
pytest backend/tests/unit/test_subvencion_division_linea.py -q
```

Resultado esperado: verde.

## Escenario 3 — Generar y descargar PDF de libros oficiales (US2)

### Pasos
1. `POST /api/v1/libros/2025/generar` (ejercicio cerrado) con `{tipos:["diario","mayor"]}` → 201 con `sha256`.
2. `GET /api/v1/libros/{id}/descarga` → PDF descargable.
3. Intentar sobre un ejercicio abierto → **409**.

### Verificación
- El PDF contiene todos los asientos numerados del ejercicio y la suma Debe==Haber del cierre (contrato `libros-pdf.md`).

```bash
pytest backend/tests/contract/test_libros_pdf_esquema.py -q
```

Resultado esperado: 201/200/409 y tests de contrato verdes.

## Escenario 4 — Emitir legalización y re-emisión con huella (US2)

### Pasos
1. `POST /api/v1/legalizaciones` con `{ejercicio: 2025}` → 201 con `huella`, rango de asientos, empresa, ejercicio.
2. Repetir la emisión sin cambios → 201 con **huella idéntica** (re-emisión permitida).
3. Insertar manualmente un asiento con fecha dentro de 2025 (forzado en test) → la nueva emisión → **409** (huella distinta / bloqueo FR-007).

### Verificación
- La huella coincide mientras el contenido no cambie; cambia → se rechaza (clarificación integrada).

```bash
pytest backend/tests/contract/test_legalizacion_formato.py -q
pytest backend/tests/contract/test_legalizacion_ejercicios.py -q
```

Resultado esperado: verdes (re-emisión idéntica 201; contenido alterado 409).

## Escenario 5 — Caja y movimientos como asientos 570 (US3)

### Pasos
1. `POST /api/v1/cajas` con `{nombre:"Caja principal", cuenta_570_id:<570>, tipo:"caja"}` → 201.
2. `POST /api/v1/cajas/{id}/movimientos` entrada `500.0000` → 201 y se crea un asiento del motor (572→570) consultable en el diario.
3. `GET /api/v1/cajas/{id}` → saldo == 500.0000.

### Verificación
- El saldo de caja es exactamente la suma de las líneas 570 (asientos reales, no paralelos).
- Alta con una 570 ya asignada a otra caja → 409.

```bash
pytest backend/tests/integration/test_caja_movimientos.py -q
```

Resultado esperado: verde; asiento 572→570 balanceado creado por el motor.

## Escenario 6 — Arqueo con diferencia y ajuste (US3)

### Pasos
1. `POST /api/v1/cajas/{id}/arqueos` con `efectivo_contado: "480.0000"` (saldo libros 500) → 201 `diferencia: -20.0000`, estado `con_diferencia`.
2. `POST /api/v1/arqueos/{id}/aprobar` con `{asiento_ajuste_id}` (asiento que cuadra 570 con 480) → 200 `aprobada`.
3. Alternativa: `POST /api/v1/arqueos/{id}/archivar` (sin asiento) → `archivada` con diferencia **pendiente visible**.

### Verificación
- Aprobar exige el asiento de ajuste (si falta → 409); el ajuste deja 570 == efectivo contado.
- El caso `cuadra` (efectivo == saldo) se aprueba sin asiento.

```bash
pytest backend/tests/unit/test_arqueo_diferencia.py -q
pytest backend/tests/integration/test_arqueo_ajuste.py -q
```

Resultado esperado: verdes; balance del asiento de ajuste Debe==Haber.