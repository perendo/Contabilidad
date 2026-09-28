# Implementation Plan: Gestión ONG (Subvenciones, Libros Oficiales y Caja)

**Branch**: `019-gestion-ong-libros-caja` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/019-gestion-ong-libros-caja/spec.md` (incluye las aclaraciones de la sesión 2026-09-16 ya integradas).

## Summary

Módulo de gestión específico para ONG con tres bloques:

1. **Subvenciones y justificación de gastos**: registro de subvenciones (entidad concedente, programa, importe concedido, ejercicio, estado) como entidad de **control de gasto** (no genera asientos propios; la percepción del ingreso se asienta con el motor SPEC-002 fuera de la feature). Los gastos se imputan a la subvención **a nivel de línea de asiento** (clarificación: apunte de gasto concreto, parcial o total), con validación de disponible y rechazo de exceso y de doble imputación. Genera el informe de justificación (concedido/gastado/pendiente).
2. **Libros oficiales y legalización**: generación de **PDF** del diario y el mayor (y cuentas anuales si están definidas) de un ejercicio cerrado, con saldos exactos (`Decimal`); y **fichero de legalización** con empresa, ejercicio, rango de asientos, fecha y **huella** de integridad. La **re-emisión solo se permite con huella idéntica** (clarificación); si el contenido cambió, se rechaza (el ejercicio está cerrado e inmutable).
3. **Caja y caja chica**: alta de cajas/fondos soportados por una **subcuenta 570 real dedicada** (caja = subcuenta 570, clarificación); las entradas/salidas se registran como **asientos reales del motor** (SPEC-002) sobre esa 570; el **arqueo** compara saldo contable 570 con efectivo contado, registra la diferencia; una diferencia aprobada **exige asiento de ajuste enlazado** que cuadre 570 con el efectivo (clarificación); si solo se archiva, la diferencia queda como pendiente visible.

Se construye sobre el stack fijado por la constitución y el `plan.md` raíz: **FastAPI (async) + PostgreSQL 16+ + Next.js**, precisión `Decimal`/`NUMERIC(18,4)`, multi-tenancy estricto por `empresa_id`, asientos inmutables y pruebas pytest obligatorias. Depende de SPEC-001/002/004/006 (motor, cuentas, ejercicios) y se relaciona con SPEC-017 sin bloqueo.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/Next.js (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Pydantic v2; frontend Next.js (App Router). Generación de PDF: biblioteca de renderizado server-side (ReportLab) bajo la decisión D3; huella SHA-256. Reutiliza el motor de asientos multilínea (SPEC-002/006) y plan de cuentas (SPEC-001).

**Storage**: PostgreSQL 16+ (tablas multi-tenant con `empresa_id` en PK/índices; `NUMERIC(18,4)`); PDFs y ficheros de legalización como `BYTEA` + `sha256` en tablas propias.

**Testing**: pytest (unit + integración); validación de PDF/legalización con fixture y comparación de contenido/huella.

**Target Platform**: Linux server (backend API), navegador web (frontend); descarga de PDF/ficheros por el frontend.

**Project Type**: web-service (backend/frontend) sobre el plan raíz PGC de ContabilidadV1.

**Performance Goals**: PDF de libros de un ejercicio (hasta 50.000 apuntes) en <15 s; informe de justificación <1 s; arqueo <300 ms; fichero de legalización <1 s tras emitir.

**Constraints**: importes siempre `Decimal`; libros/legalización solo de ejercicios cerrados; re-legalización solo con huella idéntica; huella SHA-256 sobre el contenido canónico; un mismo gasto no se imputa dos veces; arqueo con diferencia aprobada exige asiento de ajuste.

**Scale/Scope**: 1.000+ empresas multi-tenant; decenas de subvenciones y cientos de cajas/gastos por empresa y ejercicio.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Partida doble estricta**: movimientos de caja y ajustes de arqueo se persisten como asientos del motor en transacción ACID con Debe==Haber en backend. → Cumple.
- **II. Inmutabilidad del diario**: libros se generan sobre ejercicios cerrados (asientos inmutables); los ajustes de arqueo son asientos nuevos; no se edita el diario. → Cumple.
- **III. Multi-tenancy estricto**: subvenciones, imputaciones de gasto, cajas, arqueos, PDFs y legalizaciones llevan `empresa_id` en PK/índices, derivado de sesión; pruebas de aislamiento obligatorias. → Cumple.
- **IV. Numeración correlativa**: los asientos de caja/ajuste usan la numeración del motor por (empresa, ejercicio); la legalización referencia el rango ya asignado sin inventar numeración. → Cumple.
- **V. Pruebas obligatorias**: pytest unit + integración (balance estricto de caja/ajustes y aislamiento multi-tenant de subvenciones/libros/cajas). → Cumple.
- **Decimal/no float**: importes y huella calculada sobre representación canónica decimal. → Cumple.
- **Auditoría inmutable** (misma transacción ACID): subvenciones, imputaciones, emisiones de PDF/legalización, cajas, movimientos y arqueos se auditan. → Cumple.

Sin violaciones. Las decisiones de **subcuenta 570 real por caja**, **imputación de gasto a nivel de línea** y **asiento de ajuste obligatorio en arqueo con diferencia aprobada** (todas clarificaciones integradas) y la **re-legalización solo con huella idéntica** están reflejadas en `research.md` y `data-model.md`.

## Project Structure

### Documentation (this feature)

```text
specs/019-gestion-ong-libros-caja/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
│   ├── api-contracts.md
│   ├── libros-pdf.md    # Formato de los PDF de libros oficiales
│   └── legalizacion.md  # Formato del fichero de legalización
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
backend/
└── src/
    ├── models/
    │   ├── acct/            # Plan de cuentas, asientos, ejercicios (SPEC-001/002/004)
    │   └── ngo/             # subvencion.py, gasto_imputado.py, libro_oficial.py,
    │                        # legalizacion.py, caja.py, movimiento_caja.py, arqueo.py
    ├── services/
    │   └── ngo/             # subvenciones.py, justificacion.py, libros_pdf.py,
    │                        # legalizacion.py, caja.py, arqueo.py
    ├── api/
    │   └── ngo/             # routers (ver contracts/)
    └── config.py

backend/
└── tests/
    ├── unit/                # disponibles, division de gasto, huella, arqueo
    ├── integration/         # justificación, PDF/libros, legalización, caja
    └── contract/            # esquemas PDF/legalización + aislamiento multi-tenant

frontend/
└── src/
    ├── app/
    │   ├── subvenciones/    # lista, alta/edición, justificación, informe
    │   ├── libros/          # generación PDF, descarga, legalización
    │   └── caja/            # cajas, movimientos, arqueos
    ├── components/ngo/
    └── services/            # cliente HTTP con cabecera empresa activa

frontend/
└── tests/
```

**Structure Decision**: Se adopta la estructura web del `plan.md` raíz. La feature 019 aporta el módulo `ngo/` (models/services/api) y consume el motor SPEC-002/006 para todos los asientos (caja y ajustes), de modo que numeración, balance, ejercicio y auditoría sigan gobernados por el motor. Los dos formatos externos (PDF de libros y fichero de legalización) se documentan en `contracts/libros-pdf.md` y `contracts/legalizacion.md`.

## Complexity Tracking

No aplica (sin violaciones de constitución).

## Design Artifacts

- **research.md** (Phase 0): decisiones de subvenciones/justificación, libros PDF, legalización (huella/re-emisión), caja 570 y arqueo con ajuste.
- **data-model.md** (Phase 1): entidades `Subvencion`, `GastoImputado`, `LibroOficial`, `Legalizacion`, `Caja`, `Arqueo` (movimientos = asientos del motor).
- **contracts/** (Phase 1): contrato de API REST + formatos de PDF de libros y fichero de legalización.
- **quickstart.md** (Phase 1): escenarios de validación ejecutables.