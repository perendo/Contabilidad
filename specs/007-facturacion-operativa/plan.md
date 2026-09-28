# Implementation Plan: Facturación Operativa

**Branch**: `007-facturacion-operativa` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/007-facturacion-operativa/spec.md` (incluye aclaraciones integradas: recargo de equivalencia FR-010 y criterio de caja FR-011)

## Summary

Módulo de facturación operativa que permite emitir facturas de venta/compra con líneas, IVA, IRPF, recargo de equivalencia y régimen de criterio de caja, con numeración correlativa por serie y ejercicio (constitución IV), generación automática del asiento contable vinculado balanceado (motor SPEC-002/SPEC-006), y facturas rectificativas/abono con asiento de anulación sin tocar el asiento original (inmutabilidad II). Integra con el maestro de terceros (SPEC-008) para clientes/proveedores.

Se construye sobre el stack fijado por la constitución y el `plan.md` raíz: **FastAPI (async) + PostgreSQL 16+ + Next.js**, precisión `Decimal`/`NUMERIC(18,4)`, multi-tenancy estricto por `empresa_id`, asientos inmutables y pruebas pytest obligatorias.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/Next.js (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Pydantic v2; frontend Next.js (App Router). No se añaden dependencias nuevas; se consume el motor de asientos (SPEC-002/006) y el maestro de terceros (SPEC-008).

**Storage**: PostgreSQL 16+ (tablas multi-tenant con `empresa_id` en PK/índices; `NUMERIC(18,4)`). Tablas nuevas: `Factura`, `FacturaLinea`, `SerieFactura`.

**Testing**: pytest (unit + integración); cuadre del asiento generado, correlatividad de numeración, aislamiento multi-tenant.

**Target Platform**: Linux server (backend API), navegador web (frontend).

**Project Type**: web-service (backend/frontend) sobre el plan raíz PGC de ContabilidadV1.

**Performance Goals**: emisión de factura con asiento en <500 ms; consulta de factura <200 ms p95; listado de facturas páginas <200 ms p95.

**Constraints**: precisión decimal estricta en cálculo de IVA/IRPF/recargo; numeración sin saltos por (empresa_id, serie, ejercicio); bloqueo de emisión en ejercicio cerrado; config de IVA/IRPF por empresa/cuenta.

**Scale/Scope**: 1.000+ empresas multi-tenant; volumen típico de decenas a miles de facturas al mes; operación puntual.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Partida doble estricta**: el asiento generado por cada factura cuadra Debe==Haber en `Decimal`; validación en backend, no en UI. → Cumple.
- **II. Inmutabilidad del diario**: la factura rectificativa genera un asiento de anulación nuevo enlazado al original; el asiento original no se modifica ni elimina; facturas emitidas no se borran. → Cumple.
- **III. Multi-tenancy estricto**: todas las tablas (factura, serie, líneas) incluyen `empresa_id` en PK/índices/filtros derivado de sesión; pruebas de aislamiento obligatorias. → Cumple.
- **IV. Numeración correlativa**: número de factura correlativo por (empresa_id, serie, ejercicio), sin reutilizar números anulados, asignado atómicamente dentro de la misma transacción (secuencia bloqueada). → Cumple.
- **V. Pruebas obligatorias**: pytest unit + integración (cuadre del asiento y aislamiento multi-tenant). → Cumple.
- **Decimal/no float**: importes de facturas, impuestos y asientos en `Decimal`/`NUMERIC(18,4)`. → Cumple.
- **Auditoría inmutable** (misma transacción ACID): emisión, rectificación y anulación de facturas se auditan. → Cumple.

Sin violaciones. Las aclaraciones de recargo de equivalencia (FR-010) y criterio de caja (FR-011) están justificadas en `research.md`.

## Project Structure

### Documentation (this feature)

```text
specs/007-facturacion-operativa/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── api-contracts.md
│   └── factura-format.md# Estructura de la factura (cabecera, líneas, impuestos)
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
backend/
└── src/
    ├── models/
    │   ├── invoice/         # factura.py, factura_linea.py, serie_factura.py
    │   └── acct/            # JournalEntry, JournalEntryLine (SPEC-002/006)
    ├── services/
    │   └── invoicing/       # numeracion.py, calculo_impuestos.py, emision.py, rectificacion.py
    │       ├── asiento_factura.py  # generador del asiento vinculado
    │       ├── recargo_equivalencia.py  # cálculo FR-010
    │       └── criterio_caja.py     # diferimiento FR-011 para SPEC-012
    ├── api/
    │   └── invoicing.py     # endpoints de facturación
    └── config.py

backend/
└── tests/
    ├── unit/                # cálculo impuestos, numeración, asiento generado
    ├── integration/         # emisión, rectificación, aislamiento multi-tenant
    └── contract/            # firma de contratos de API

frontend/
└── src/
    ├── app/
    │   └── facturacion/     # listado, creación, detalle, rectificativa
    │       ├── facturas/
    │       └── series/      # configuración de series
    └── components/
        │   └── invoicing/   # invoice-form con líneas dinámicas
    └── services/
        └── client.ts

frontend/
└── tests/
```

**Structure Decision**: Se adopta la estructura web (backend/frontend) del `plan.md` raíz: `backend/src/models/invoice/` y `backend/src/services/invoicing/` para esta feature; `frontend/src/app/facturacion/` para las páginas de facturas/series. Los generadores de asiento consumen el motor de SPEC-002/006.

## Complexity Tracking

No aplica (sin violaciones de constitución).

## Design Artifacts

- **research.md** (Phase 0): decisiones de estructura de factura, cálculo de impuestos, recargo de equivalencia, criterio de caja, correlatividad y vínculo al asiento.
- **data-model.md** (Phase 1): entidades `Factura`, `FacturaLinea`, `SerieFactura`.
- **contracts/** (Phase 1): contrato de API REST y estructura de la factura (cabecera, líneas, impuestos, descuentos).
- **quickstart.md** (Phase 1): escenarios de validación ejecutables.