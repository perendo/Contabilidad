# Implementation Plan: Documentos adjuntos al asiento (SPEC-030)

**Branch**: `030-documentos-asiento` | **Date**: 2026-09-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/030-documentos-asiento/spec.md`

**Note**: todas las decisiones tecnicas estan resueltas en [research.md](research.md) (D1..D22). No quedan NEEDS CLARIFICATION.

## Summary

Anadir evidencia documental al diario contable: el usuario adjunta uno o varios ficheros PDF
o imagen (JPEG, PNG, TIFF) a un asiento, los vuelve a consultar y descargar desde el detalle,
y el sistema garantiza que ese contenido no se altera ni se retira silenciosamente. El
contenido se almacena como `BYTEA` en una tabla propia `documento_asiento` con huella SHA-256,
FK compuesta a `journal_entry` por `empresa_id`, unicidad `(empresa_id, journal_entry_id,
sha256)`, inmutabilidad del contenido por trigger, baja logica solo en asientos `DRAFT` y traza
de altas y bajas en el `audit_log` WORM ya existente. Los permisos reutilizan el modulo `acct`
(`crear` para adjuntar, `baja` para dar de baja, `ver` para listar y descargar). No se anade
ninguna dependencia de frontend; la previsualizacion usa el visor nativo del navegador sobre una
URL de objeto creada en cliente.

**La adjuncion es siempre opcional** (FR-020, aclaracion expresa del usuario): ningun asiento
esta obligado a tener documentos y ninguna operacion contable, fiscal o de cierre depende de
que los tenga.

## Technical Context

**Language/Version**: Python 3.11+ (backend) · TypeScript 5.7 / Next.js 15.5 + React 19 (frontend)

**Primary Dependencies**: FastAPI 0.141 (async) · SQLAlchemy 2.0 async + asyncpg · Pydantic v2 ·
pydantic-settings · PyJWT · python-multipart · **pypdf** (ya declarada) · **Pillow** (nueva
declaracion, ver D8) · pytest 8.4 / pytest-asyncio · ruff · mypy

**Storage**: PostgreSQL 16+ (`BYTEA` para el contenido, `NUMERIC(18,4)` para el importe
informativo, `TIMESTAMPTZ` UTC para las fechas). Tests sobre SQLite en memoria con
`StaticPool`, `PRAGMA foreign_keys=ON` y triggers espejados; verificacion opt-in sobre
PostgreSQL real con `TEST_DATABASE_URL`.

**Testing**: pytest (unit + integration en `backend/tests/{unit,integration}`), contrato
PostgreSQL en `tests/integration/test_pg_schema.py`, migraciones en
`tests/unit/test_migrations.py`. Frontend: `tsc --noEmit`, `eslint src` y `next build` (no hay
runner de tests en frontend).

**Target Platform**: servidor Linux en produccion; desarrollo en Windows. Node 20 para el
frontend. Sin componentes moviles.

**Project Type**: web-service (FastAPI) + SPA (Next.js App Router), multi-empresa.

**Performance Goals**
- Adjuntar un documento: menos de 60 s de tiempo percibido por el usuario, sin abandonar la
  pantalla del asiento (SC-001).
- Consultar y descargar un documento: menos de 3 s (SC-002).
- El detalle de un asiento sigue siendo usable con 20 o mas documentos adjuntos (SC-008).
- El limite operativo por defecto es 50 documentos por asiento, superior al minimo de SC-008.

**Constraints**
- 10 MB por documento (`documento_max_bytes`), 200 paginas por PDF (`documento_max_paginas`),
  50 documentos por asiento (`documento_max_por_asiento`).
- Conservacion del soporte 6 anos (`documento_plazo_conservacion_anos`, articulo 30 LGT).
- Sin OCR ni extraccion de texto; sin firma digital; sin carpetas ni ZIP.
- Prohibido `float` para importes: `importe_informativo` es `NUMERIC(18,4)` con `Decimal`.
- La adjuncion nunca escribe en `journal_entry` ni en `journal_entry_line` (SC-007).
- El prefijo de API es `/api/v1/...` y `empresa_id` se deriva siempre de la sesion.

**Scale/Scope**
- 1 tabla nueva (`documento_asiento`) + 2 enums, en la migracion `021_adjuntos_asiento.sql`.
  (El numero previsto era 018, que ya ocupa `018_cashflow.sql` de SPEC-027; se usa el
  siguiente libre.)
- 1 modulo de servicio nuevo (`services/documentos/`) con 5 modulos: `errores`,
  `validacion`, `adjuntos`, `consulta` y `bajas`.
- 1 router de API nuevo con 6 endpoints, todos bajo el modulo RBAC `acct`
  (1 POST + 4 GET + 1 DELETE; ver `contracts/api-contracts.md` seccion 7).
- 1 componente nuevo de frontend (`components/documentos/`) y 2 pantallas.
- Sin cambios en SPEC-002: el asiento no se modifica en ningun punto.
- Sin modulo RBAC nuevo, sin cambios en los `Settings` existentes.

## Constitution Check

*GATE: evaluado antes de Phase 0 y re-evaluado despues del diseno de Phase 1. Sin violaciones
sin justificar.*

| Principio / norma | Exigencia | Como se cumple | Estado |
|---|---|---|---|
| I. Partida doble estricta | Ningun asiento desbalanceado; validacion en el backend | La operacion no toca `journal_entry` ni `journal_entry_line`; solo inserta filas hijas. SC-007 verifica que el cuadre se mantiene antes y despues | PASS |
| II. Inmutabilidad del diario | Sin `UPDATE`/`DELETE` de `POSTED`, garantia a nivel de BD | El asiento no se modifica. El contenido del documento queda bloqueado por trigger `BEFORE UPDATE` restringido y `BEFORE DELETE` (D3). La baja solo se permite en `DRAFT` (FR-010) y la correccion se hace por `REVERSAL`, como ya hace SPEC-002 | PASS |
| III. Multi-tenancy estricto | `empresa_id` derivado de la sesion, presente en claves, indices y filtros | `Depends(get_empresa_id)` en las 5 rutas; `UNIQUE (empresa_id, id)`; FK compuesta `(empresa_id, journal_entry_id)`; indices por `empresa_id`; referencia ajena devuelve 404 indistinguible de "no existe" (D14) | PASS |
| IV. Numeracion y correlatividad | Secuencia atomica sin saltos | Los documentos no llevan numero correlativo ni secuencia que asignar; no aplica a esta entidad | N/A justificado |
| V. Pruebas obligatorias | pytest que verifique balance y aislamiento multi-tenant | Plan de tests en `quickstart.md`: aislamiento en las 5 rutas, cuadre intacto tras adjuntar y tras dar de baja, inmutabilidad por trigger, y unicidad de huella | PASS |
| Precision decimal | `Decimal` en Python, `NUMERIC(18,4)` en PostgreSQL, prohibido `float` | `importe_informativo NUMERIC(18,4)`, validado con `Decimal`, serializado como string de 4 decimales (D19) | PASS |
| Auditoria y trazabilidad | Registro inmutable en la misma transaccion ACID | `registrar_auditoria` escribe en `audit_log` dentro del boundary de `get_db`; `audit_log` ya tiene triggers WORM (D5) | PASS |
| Transacciones ACID | Cabecera y lineas indivisibles | La cabecera del documento y su traza de auditoria se persisten juntas en la misma sesion; la cabecera y las lineas del asiento no se ven afectadas (ver desviacion V1) | PASS con desviacion justificada |
| Contexto de empresa en frontend | `empresa_id` en cabeceras y recalculo al cambiar de empresa | Se usa `cabecerasEmpresa()` desde `services/client.ts`; el cambio de empresa ya invalida via `CompanySwitch` | PASS |
| Entrada contable por teclado | UI usable por teclado | El selector es un `<input type="file">` nativo y la accion un `<button>` nativo: navegables por teclado sin codigo adicional | PASS |
| Endpoints `/api/v1/...` | Prefijo versionado | `APIRouter(prefix="/api/v1/documentos")` | PASS |

**Constitution Check re-evaluado tras Phase 1**: sin cambios. Las unicas desviaciones son V1 y
V2, ambas recogidas en Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/030-documentos-asiento/
├── spec.md                       # /speckit.specify
├── plan.md                       # This file (/speckit.plan command output)
├── research.md                   # Phase 0 output (D1..D22)
├── data-model.md                 # Phase 1 output
├── quickstart.md                 # Phase 1 output
├── contracts/
│   └── api-contracts.md          # Phase 1 output
├── checklists/
│   ├── requirements.md           # built-in spec-quality lifecycle
│   └── requirements-quality.md   # custom checklist (44 items)
└── tasks.md                      # Phase 2 output (/speckit.tasks, NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
backend/
├── requirements.txt (raiz) -> anadir pillow>=10.0,<13.0
├── migrations/
│   └── 021_adjuntos_asiento.sql              # NUEVO: tabla, enums, FKs, unicidades, triggers
├── src/
│   ├── main.py                               # registrar documentos_router
│   ├── config.py                             # +4 campos en Settings
│   ├── api/
│   │   └── documentos/                  # NUEVO: paquete con router
│   │       ├── __init__.py              #   solo AGREGA los sub-routers (ver nota)
│   │       ├── deps.py                  #   Db, Empresa, _http(), ACTOR
│   │       ├── adjuntos.py              #   POST   (US1)
│   │       ├── consulta.py              #   GET x4 (US2)
│   │       └── bajas.py                 #   DELETE (US3)
│   ├── models/
    |   |   |   __init__.py                       # +acct ya registrado; exportar documento
│   │   └── acct/
│   │       ├── __init__.py                   # +DocumentoAsiento
│   │       └── documento.py                  # NUEVO: DocumentoAsiento, TipoDocumento, EstadoDocumento
│   ├── services/
│   │   └── documentos/
│   │       ├── __init__.py              # NUEVO
│   │       ├── errores.py               # NUEVO: DocumentoError + error()
│   │       ├── validacion.py            # NUEVO: firmas, pypdf, Pillow, tamano, paginas
│   │       ├── adjuntos.py              # NUEVO: adjuntar y validar en lote (US1)
│   │       ├── consulta.py              # NUEVO: listar, obtener, datos de descarga (US2)
│   │       └── bajas.py                 # NUEVO: baja logica y recuperacion (US3)
│   ├── db/
│   │   ├── migrate.py                        # +021 en ORDEN_PREFERENTE (al final)
│   │   └── triggers.py                       # +espejo SQLite de los 2 triggers
│   └── tests/
│       ├── conftest.py                       # +fixture documentos_client
│       ├── unit/
│       │   ├── test_migrations.py             # +018 en ESPERADAS + test de contenido
│       │   ├── test_documento_validacion.py   # NUEVO
│       │   ├── test_documento_adjuntos.py     # NUEVO
│       │   ├── test_documento_isolation.py    # NUEVO
│       │   └── test_constitucion_documentos.py# NUEVO
│       └── integration/
│           ├── test_documentos_routes.py      # NUEVO
│           ├── test_documentos_tenant.py      # NUEVO
│           ├── test_documentos_opcional.py    # NUEVO: FR-020
│           └── test_pg_schema.py              # +contrato de 018
└── frontend/
    ├── src/
    │   ├── app/
    │   │   ├── page.tsx                      # +enlace a /documentos
    │   │   ├── asientos/[id]/page.tsx         # +seccion de documentos (opcional)
    │   │   └── documentos/
    │   │       └── page.tsx                   # NUEVO: listado global con filtros
    │   └── components/
│       └── documentos/
│           ├── api.ts                     # NUEVO: tipos + cliente tipado
│           ├── DocumentosAsiento.tsx      # NUEVO: selector multiple, lista, estado vacio
│           └── VisorDocumento.tsx         # NUEVO: previsualizacion y descarga autenticada
```

**Nota de prefijo (research D7)**: el prefijo `/api/v1/documentos` lo declara
**cada sub-router**, no el padre. La ruta del listado global es exactamente `""`, y
FastAPI rechaza un `include_router` con prefijo y camino ambos vacios; el padre se
limita a agregar. Es el criterio de `api/costcenters/` (SPEC-017), no una preferencia.

**Structure Decision**: se mantiene la estructura real del repositorio (backend Python con
`models`/`services`/`api`/`db` y frontend Next.js con `app`/`components`), que es la que usan
las 30 specs anteriores. El API es un **paquete** `api/documentos/` y no un modulo suelto: cada
historia de usuario aporta un fichero propio (`adjuntos.py`, `consulta.py`, `bajas.py`), de modo
que US1, US2 y US3 se puedan implementar en paralelo sin editar el mismo fichero. Esto sigue el
precedente de `api/ngo/` y `api/treasury/`, y evita el conflicto de ficheros que generaria un
`api/documentos.py` unico. La lista y el selector viven en
`components/documentos/DocumentosAsiento.tsx` y la previsualizacion en
`components/documentos/VisorDocumento.tsx`, de modo que el estado vacio que declara la
opcionalidad y el comportamiento de descarga se escriben una sola vez.

## Complexity Tracking

> Relleno solo para las desviaciones de la constitution que deben justificarse.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| V1. El boundary ACID es `get_db` + `flush()` del servicio, no `async with async_session.begin()` como dice literalmente la constitution | Es el patron ya establecido en todo el repositorio (SPEC-002, 005, 006, 007, 010, 016, 020-026) y documentado en AGENTS.md secciones 24, 33 y 36. `get_db` hace commit al final de la peticion y rollback ante excepcion, que es un boundary equivalente y mas estrecho que una transaccion por servicio | Adoptar `async_session.begin()` exigiria reestructurar todos los servicios existentes y los haria incompatibles entre si; el resultado funcional seria identico |
| V2. Se reutiliza el modulo RBAC `acct` en lugar de crear un modulo `documentos` propio | No es una violacion de la constitution sino una desviacion del patron por-feature de SPEC-017, SPEC-019 y SPEC-026. FR-016 pide un permiso para adjuntar y otro diferenciable para dar de baja, y `acct` ya ofrece `crear` y `baja`. Un modulo propio obligaria a cambiar de forma coherente `services/security/catalogo.py`, `migrations/007_rbac.sql`, `db/triggers.py` y tres recuentos de tests, sin aportar granularidad real | Crear el modulo `documentos`: rechazado por coste de mantenimiento desproporcionado (D4). Queda abierto si el gestor documental se independiza en el futuro |
