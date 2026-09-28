# Implementation Plan: Remesas SEPA y Soporte Magnético

**Branch**: `020-remesas-sepa-cobros` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/020-remesas-sepa-cobros/spec.md`

## Summary

Módulo de tesorería que agrupa recibos (vencimientos de SPEC-011) en remesas de domiciliación y genera el fichero de cobro en formato **XML SEPA DD (PAIN.008, tipo CORE por defecto, B2B opcional)** y **CSB 19.19** (AEB), descargable para el banco. Una remesa puede contener varias fechas de vencimiento y cada fichero las representa en grupos separados por fecha de cargo. Incluye **descuento por pronto pago** configurado por tercero (SPEC-008) con override por factura (asiento 432/662 contra 430), y el **procesado de devoluciones R19/C19** que revierte el cobro con un asiento `REVERSAL` (inmutabilidad de la constitución) y reabre el vencimiento. El cobro se confirma por marcado manual o conciliación bancaria idempotente (SPEC-013); no hay descarga automática de confirmaciones bancarias.

Se construye sobre el stack fijado por la constitución y el `plan.md` raíz: **FastAPI (async) + PostgreSQL 16+ + Next.js**, precisión `Decimal`/`NUMERIC(18,4)`, multi-tenancy estricto por `empresa_id`, asientos inmutables y pruebas pytest obligatorias.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/Next.js (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Pydantic v2; frontend Next.js (App Router). Generación SEPA: biblioteca XML estándar (o plantilla `PAIN.008.001.02` propia); CSB 19.19: generador propio de texto plano AEB.

**Storage**: PostgreSQL 16+ (tablas multi-tenant con `empresa_id` en PK/índices; `NUMERIC(18,4)`).

**Testing**: pytest (unit + integración); validación de ficheros generados con esquema + fixtures.

**Target Platform**: Linux server (backend API + worker), navegador web (frontend).

**Project Type**: web-service (backend/frontend) sobre el plan raíz PGC de ContabilidadV1.

**Performance Goals**: generación de remesa de hasta 5.000 recibos en <10 s; respuesta de consulta de remesas <200 ms p95 bajo 100 usuarios concurrentes; publicación del fichero < 500 ms tras emitir.

**Constraints**: <200 ms p95 en listados; fichero SEPA/CSB válido según esquema EPC/AEB y agrupado por fecha de cargo; importes siempre con `Decimal`; mandatos B2B firmados antes de emitir; plazos de primera CORE (D-2), CORE recurrente según mandato/banco y B2B (D-1) validados antes de emitir.

**Scale/Scope**: 1.000+ empresas multi-tenant, remesas de decenas a miles de recibos; ficheros de hasta ~5 MB.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Partida doble estricta**: todo asiento (cobro, descuento, reversión de devolución) debe cuadrar Debe==Haber en backend. → Cumple; se valida en servicio, no en UI.
- **II. Inmutabilidad del diario**: la devolución R19/C19 genera un asiento `REVERSAL` nuevo enlazado; el asiento original del cobro no se toca. → Cumple.
- **III. Multi-tenancy estricto**: todas las tablas (remesas, recibos, devoluciones, condiciones, mandatos) incluyen `empresa_id` en índices únicos y FKs compuestas, además de filtros derivados de sesión; pruebas de aislamiento obligatorias. → Cumple.
- **IV. Numeración correlativa**: número de remesa por `empresa_id` + ejercicio, asignado atómicamente dentro de la misma transacción (secuencia bloqueada). → Cumple; se planifica secuencia PostgreSQL por (empresa, ejercicio).
- **V. Pruebas obligatorias**: pytest unit + integración (balance estricto y aislamiento multi-tenant). → Implementadas y ejecutadas; el cierre documental permanece pendiente hasta completar T054, T055, T056 y T062.
- **Decimal/no float**: importes en `Decimal`/`NUMERIC(18,4)` en todo el flujo SEPA y asientos. → Cumple.
- **Auditoría inmutable** (misma transacción ACID): remesas, emisiones, cobros manuales/conciliados, devoluciones y liquidaciones de descuento se auditan. → Cumple.

No se han detectado violaciones constitucionales en la implementación verificada. La decisión de formato dual (SEPA + CSB 19.19) y la confirmación de cobro manual/conciliación están justificadas en `research.md`. El plan permanece pendiente de cierre documental hasta completar T054, T055, T056 y T062.

## Project Structure

### Documentation (this feature)

```text
specs/020-remesas-sepa-cobros/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
backend/
└── src/
    ├── models/
    │   ├── acct/            # Plan de cuentas, asientos (SPEC-001/002)
    │   ├── ar/              # Terceros, vencimientos, cobros (SPEC-008/011)
    │   └── treasury/        # remesa.py, recibo_remesa.py, devolucion.py,
    │                        # condicion_pronto_pago.py, mandato_sepa.py
    ├── services/
    │   ├── remittance/      # seleccion, numero correlativo, emision, fichero
    │   │   ├── sepa_dd.py   # generador PAIN.008.001.02 + mandatos
    │   │   ├── csb_1919.py  # generador AEB 19.19
    │   │   └── refund_r19.py# parseo R19/C19 + REVERSAL
    │   └── discount.py      # descuento por pronto pago (432/662 vs 430)
    ├── api/                 # endpoints (ver contracts/)
    └── config.py

backend/
└── tests/
    ├── unit/                # generadores SEPA/CSB, descuento, correlatividad
    ├── integration/         # emision de remesa, devolucion con REVERSAL
    └── contract/            # firma de contratos de API + aislamiento mult-tenant

frontend/
└── src/
    ├── app/
    │   ├── remesas/         # listado, creación, detalle, descarga
    │   ├── devoluciones/    # importación R19/C19, reclamaciones
    │   └── terceros/        # condiciones de pronto pago (SPEC-008)
    └── services/            # cliente HTTP con cabecera empresa activa

frontend/
└── tests/
```

**Structure Decision**: Se adopta la estructura web (backend/frontend) del `plan.md` raíz: `backend/` con separación models/services/api y módulo `treasury/` para esta feature; `frontend/` con las páginas de remesas/devoluciones. La feature 020 aporta `services/remittance` (generadores SEPA/CSB y procesado R19) reutilizando models de `ar/` y `acct/`.

## Complexity Tracking

No aplica: no se han detectado violaciones constitucionales, pero el cierre documental sigue pendiente de T054, T055, T056 y T062.

## Design Artifacts

- **research.md** (Phase 0): decisiones de formato SEPA/CSB, mandatos, plazos, correlatividad y confirmación de cobro.
- **data-model.md** (Phase 1): entidades `Remesa`, `ReciboRemesa`, `DevolucionRecibo`, `Reclamacion`, `CondicionProntoPago`, `MandatoSepa`.
- **contracts/** (Phase 1): contrato de API REST y esquemas de fichero (SEPA PAIN.008.001.02, CSB 19.19, R19/C19).
- **quickstart.md** (Phase 1): escenarios de validación ejecutables.