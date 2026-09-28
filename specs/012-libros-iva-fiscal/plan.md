# Implementation Plan: Libros de IVA y Modelos Fiscales

**Branch**: `012-libros-iva-fiscal` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/012-libros-iva-fiscal/spec.md`

## Summary

Modulo fiscal que construye los **libros de registro de IVA** (emitidas, recibidas e intracomunitarias) automaticamente a partir de las facturas (SPEC-007) y sus asientos, sin entrada manual. Calcula los **modelos 303** (autoliquidacion trimestral/mensual) cuadrados con los libros, prepara el **modelo 347** (operaciones con terceros por NIF y clave) y el **349** (intracomunitarias), y **exporta** los modelos en fichero legible para presentacion con trazabilidad del periodo. Incorpora los regimenes especiales de **recargo de equivalencia** (cuota separada con su cuenta) y **criterio de caja** (IVA diferido hasta el cobro/pago, trazado por vencimientos de SPEC-011). El enlace **SII** queda declarado como interfaz opcional habilitable por empresa, sin envio ejecutado (integra con SPEC-029).

Se construye sobre el stack fijado por la constitucion y el `plan.md` raiz: **FastAPI (async) + PostgreSQL 16+ + Next.js**, precision `Decimal`/`NUMERIC(18,4)`, multi-tenancy estricto por `empresa_id`, asientos inmutables y pruebas pytest obligatorias.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript/Next.js (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async + asyncpg, Pydantic v2; frontend Next.js (App Router). Generacion de exportacion de modelos: XML y fichero de texto propietario AEAT (303/347/349); interfaz SII: mapeo a esquema XML `SuministroInfo/...` (sin envio en esta feature).

**Storage**: PostgreSQL 16+ (tablas multi-tenant con `empresa_id` en PK/indices; `NUMERIC(18,4)`).

**Testing**: pytest (unit + integracion); verificacion de cuadres de cuotas y aislamiento multi-tenant.

**Target Platform**: Linux server (backend API), navegador web (frontend).

**Project Type**: web-service (backend/frontend) sobre el plan raiz PGC de ContabilidadV1.

**Performance Goals**: construccion de libro de IVA de un trimestre en <10 s; calculo del 303 <5 s; exportacion de un periodo <2 s; consultas <200 ms p95.

**Constraints**: los libros se derivan SOLO de facturas/asientos (sin entrada manual); los modelos cuadran con los libros; cuotas de recargo separadas; IVA de caja diferido trazado; exportaciones identifican periodo y empresa; SII opcional por empresa.

**Scale/Scope**: 1.000+ empresas multi-tenant; miles de facturas por trimestre; ficheros de exportacion de hasta ~10 MB.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Partida doble estricta**: los libros se derivan de asientos que ya cumplen Debe==Haber; el cuadre 303 se verifica en backend. → Cumple.
- **II. Inmutabilidad del diario**: los libros no mutan asientos; la regeneracion de un periodo exportado se registra con trazabilidad y advertencia, sin alterar asientos POSTED. → Cumple.
- **III. Multi-tenancy estricto**: todas las tablas (libros, periodos, exportaciones, configuracion SII) incluyen `empresa_id` en PK/indices/filtros derivado de sesion. → Cumple.
- **IV. Numeracion correlativa**: numero de exportacion/periodo por (empresa, ejercicio) asignado atomicamente. → Cumple.
- **V. Pruebas obligatorias**: pytest unit + integracion (cuadre 303 y aislamiento multi-tenant). → Cumple.
- **Decimal/no float**: bases, cuotas, recargo y resultado en `Decimal`/`NUMERIC(18,4)`. → Cumple.
- **Auditoria inmutable** (misma transaccion ACID): exportaciones, regeneraciones y cambios de configuracion se auditan. → Cumple.

Sin violaciones.

## Project Structure

### Documentation (this feature)

```text
specs/012-libros-iva-fiscal/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── api-contracts.md
│   ├── modelos-fiscales.md
│   └── sii-xml.md
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
backend/
└── src/
    ├── models/
    │   ├── fiscal/         # libro_iva.py, periodo_fiscal.py,
    │   │                   # exportacion_modelo.py, configuracion_sii.py
    │   └── acct/           # Plan de cuentas, asientos (SPEC-001/002)
    ├── services/
    │   ├── vat/            # libros_iva.py, periodo.py, modelos.py,
    │   │                   # exportacion.py, recargo_equivalencia.py,
    │   │                   # criterio_caja.py, sii.py
    │   └── journal/        # Servicio de asientos (SPEC-002)
    ├── api/
    │   ├── libros_iva.py   # Libros de IVA
    │   ├── modelos.py      # Calculo 303/347/349
    │   ├── exportaciones.py# Exportacion de modelos
    │   └── sii.py          # Configuracion SII (interfaz)
    └── config.py

backend/
└── tests/
    ├── unit/                # cuadres, regimenes especiales, exportacion
    ├── integration/         # libros completos, modelos, multi-tenant
    └── contract/            # firma de contratos de API + esquemas fiscales

frontend/
└── src/
    ├── app/
    │   ├── libros-iva/      # libros emitidas/recibidas/intracomunitarias
    │   ├── modelos/         # 303, 347, 349
    │   └── exportaciones/   # ficheros generados y trazabilidad
    └── components/
        └── vat/             # componentes de IVA/fiscal
```

**Structure Decision**: Se crea el modulo `fiscal/` para entidades de IVA y `services/vat` para la logica. La reconstruccion de libros deriva de facturas/asientos existentes; el calculo de modelos reutiliza `libros_iva`. El SII queda como configuracion + mapeo XML sin envio.

## Complexity Tracking

No aplica (sin violaciones de constitucion).

## Design Artifacts

- **research.md** (Phase 0): decisiones de construccion de libros, cuadre 303, exportacion, recargo de equivalencia, criterio de caja y SII.
- **data-model.md** (Phase 1): entidades `LibroIVA`, `PeriodoFiscal`, `ExportacionModelo`, `ConfiguracionSII`, regimenes especiales.
- **contracts/** (Phase 1): contrato de API REST y esquemas de modelos fiscales (303/347/349) y XML SII.
- **quickstart.md** (Phase 1): escenarios de validacion ejecutables.