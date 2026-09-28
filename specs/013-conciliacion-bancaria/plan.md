# Implementation Plan: Conciliación Bancaria

**Branch**: `013-conciliacion-bancaria` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/013-conciliacion-bancaria/spec.md`

## Summary

Módulo de tesorería que **importa los extractos de las cuentas bancarias 572** de la empresa activa en formato interoperable **norma 43/19** (fichero de movimientos generado por la banca), con **detección de duplicados** (huella `sha256` + reglas de negocio). A partir de los movimientos del extracto, el sistema **propone cruces automáticos** con los apuntes contables de la cuenta 572 (SPEC-001/002) por importe, orientación deudora/acreedora y concepto, y permite el **cruce manual trazable** (quién y cuándo). Mantiene en todo momento, por cuenta, el **saldo según banco, saldo según libros y la diferencia por conciliar**, y al **cerrar el período conciliado** archiva solo cuando la diferencia es cero; en caso contrario advierte de los pendientes sin archivar.

La conciliación es el **mecanismo de confirmación de cobros de remesas SEPA (SPEC-020)**: cuando un movimiento del extracto se concilia con un apunte de cobro de remesa, el sistema notifica al módulo de remesas para marcar el recibo como `cobrado`. No hay integración directa con banca electrónica; la entrada son ficheros de extracto y la salida es el cruce trazable y el informe de saldos. Una operación bancaria sin apunte contable genera una **alerta**, no un asiento automático.

Se construye sobre el stack fijado por la constitución y el `plan.md` raíz: **FastAPI (async) + PostgreSQL 16+ + Next.js**, precisión `Decimal`/`NUMERIC(18,4)`, multi-tenancy estricto por `empresa_id`, asientos inmutables y pruebas pytest obligatorias.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/Next.js (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Pydantic v2; frontend Next.js (App Router). Parser de extracto: implementación propia sobre layout de ancho fijo norma 43/19 (o CSV normalizado) con configuración por entidad.

**Storage**: PostgreSQL 16+ (tablas multi-tenant con `empresa_id` en PK/índices; `NUMERIC(18,4)`; huella `sha256` para duplicados de extracto).

**Testing**: pytest (unit + integración); fixtures de ficheros de extracto (norma 43/19 y CSV) en `backend/tests/fixtures/`.

**Target Platform**: Linux server (backend API), navegador web (frontend).

**Project Type**: web-service (backend/frontend) sobre el plan raíz PGC de ContabilidadV1.

**Performance Goals**: importación de extracto de hasta 5.000 movimientos en <3 s; propuestas de cruce para un período <500 ms; informe de conciliación <200 ms p95; carga de extractos concurrentes de distintas empresas sin bloqueos.

**Constraints**: <200 ms p95 en listados/informe; importes siempre con `Decimal`; detección total de duplicados (SC-001); cruces siempre trazables (SC-002); cierre solo con diferencia cero (SC-003); aislamiento total por empresa (SC-004); precisión 4 decimales (SC-005).

**Scale/Scope**: 1.000+ empresas multi-tenant; extractos de decenas a miles de movimientos por cuenta y mes; hasta ~5 MB por fichero. Máximo de movimientos por extracto y pico de concurrencia de importaciones: NEEDS CLARIFICATION — resuelto en `research.md` (D1).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Partida doble estricta**: la conciliación no crea asientos salvo la confirmación de cobro de remesa (SPEC-020), que delega en el motor de asientos (SPEC-002) con Debe==Haber validado en backend. → Cumple.
- **II. Inmutabilidad del diario**: los apuntes contables `POSTED` de la 572 nunca se modifican ni eliminan; el cruce es una relación trazable sobre apuntes existentes. Un período conciliado `archivado` es inmutable; antes de archivar los cruces pueden deshacerse. → Cumple.
- **III. Multi-tenancy estricto**: todas las tablas (extractos, movimientos, conciliaciones, cruces, períodos, alertas) incluyen `empresa_id` en PK/índices/filtros derivado de sesión; importar un extracto de otra empresa se rechaza; pruebas de aislamiento obligatorias. → Cumple.
- **IV. Numeración correlativa**: `numero_periodo` del período conciliado correlativo por `(empresa_id, ejercicio)`, asignado atómicamente dentro de la misma transacción (secuencia bloqueada). → Cumple.
- **V. Pruebas obligatorias**: pytest unit + integración (balance estricto cuando se asienta, duplicados de extracto, cruces y aislamiento multi-tenant). → Cumple.
- **Decimal/no float**: todos los importes (saldo, movimientos, cruces, diferencia) en `Decimal`/`NUMERIC(18,4)`. → Cumple.
- **Auditoría inmutable** (misma transacción ACID): importaciones, cruces, deshaces y cierres se auditan. → Cumple.

Sin violaciones. La decisión de formato de extracto y parser parametrizable, el algoritmo de emparejamiento y el acoplamiento con SPEC-020 están justificados en `research.md`.

## Project Structure

### Documentation (this feature)

```text
specs/013-conciliacion-bancaria/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
│   ├── api-contracts.md
│   └── norma-43-19.md   # Formato externo del fichero de extracto
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
backend/
└── src/
    ├── models/
    │   ├── acct/            # Plan de cuentas, asientos (SPEC-001/002)
    │   └── treasury/        # extracto_bancario.py, movimiento_bancario.py,
    │                        # conciliacion.py, periodo_conciliado.py,
    │                        # alerta_conciliacion.py
    ├── services/
    │   └── reconciliation/  # importacion.py (parser + alta), matching.py,
    │                        # cruce.py (manual + confirmación cobro SPEC-020),
    │                        # saldos.py, cierre.py
    ├── api/                 # reconciliation.py (endpoints, ver contracts/)
    └── config.py

backend/
└── tests/
    ├── fixtures/            # extractos norma 43/19 y CSV de prueba
    ├── unit/                # parser, duplicados, matching, saldos, cierre
    ├── integration/         # importación, cruces, cierre, aislamiento
    └── contract/            # firma de contratos de API + aislamiento multi-tenant

frontend/
└── src/
    ├── app/
    │   └── conciliacion/    # importación, conciliación interactiva, informe
    ├── components/reconciliation/
    └── services/            # cliente HTTP con cabecera de empresa activa

frontend/
└── tests/
```

**Structure Decision**: Se adopta la estructura web (backend/frontend) del `plan.md` raíz: `backend/` con separación models/services/api, modelos en `models/treasury/` (comparte dominio con SPEC-020) y servicios de proceso en `services/reconciliation/`; `frontend/` con las páginas de conciliación. La feature 013 no duplica el motor de asientos de SPEC-002: solo crea la relación de cruce y, para cobros de remesa, notifica a SPEC-020.

## Complexity Tracking

No aplica (sin violaciones de constitución).

## Design Artifacts

- **research.md** (Phase 0): decisiones de formato de extracto (norma 43/19 vs CSV), detección de duplicados, algoritmo de emparejamiento, trazabilidad de cruces, saldos/cierre y acoplamiento con SPEC-020.
- **data-model.md** (Phase 1): entidades `ExtractoBancario`, `MovimientoBancario`, `Conciliacion`, `CruceConciliacion`, `PeriodoConciliado`, `AlertaConciliacion`.
- **contracts/** (Phase 1): contrato de API REST y especificación del fichero de extracto `norma-43-19.md`.
- **quickstart.md** (Phase 1): escenarios de validación ejecutables.