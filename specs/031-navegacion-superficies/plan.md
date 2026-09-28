# Implementation Plan: Navegación y superficies

**Branch**: `031-navegacion-superficies` | **Date**: 2026-09-27 | **Spec**: [link](spec.md)

**Input**: Feature specification from `/specs/031-navegacion-superficies/spec.md`

## Summary

Reordenar la aplicación contable según Material Design 3: seis superficies
navegables, una zona de contexto permanente con identidad, empresa y ejercicio
activo, páginas de inicio con resumen, favoritos por usuario y Consolidación de
las rutas duplicadas. Hoy el programa expone sus opciones en una lista plana de
24 enlaces y no existe ninguna superficie de navegación (`layout.tsx` solo
monta los dos selectores de empresa), 79 de sus 103 pantallas no son alcanzables
y el ejercicio no es un contexto.

El enfoque técnico es aditivo y de bajo riesgo para los datos contables: la
navegación es frontend, y el backend solo añade **una** lectura de contexto
(`GET /api/v1/contexto`), **una** cabecera (`X-Ejercicio-Activa`) y **una** tabla
(`favorito_usuario`, migración `022`). Ninguna de las dos toca el motor de
asientos ni altera el esquema del diario.

## Technical Context

**Language/Version**: Python 3.11+ (backend) · TypeScript con Next.js 15 App Router y React 19 (frontend)

**Primary Dependencies**: FastAPI (async) · SQLAlchemy 2.x async + asyncpg · Pydantic v2 · Next.js 15.5 · React 19 · Tailwind CSS 3.4

**Storage**: PostgreSQL 18.6 real (migraciones 000-021 aplicadas) · SQLite en memoria para la suite. **No** hay componente Material Components for Web ni MUI: la capa M3 se construye a mano sobre Tailwind.

**Testing**: pytest (unitarias, integración, contrato) · `tsc --noEmit` · ESLint · `next build`

**Target Platform**: Web de escritorio como principal (aplicación contable, uso diario intensively) · web móvil como secundaria (consulta y captured en Mobility)

**Project Type**: web-service + web-app (backend FastAPI y frontend Next.js en el mismo repositorio)

**Performance Goals**: el cambio de empresa o de ejercicio MUST sentirse inmediato. Objetivo p95 < 300 ms para `GET /api/v1/contexto` y para el cambio de contexto en cliente. Derivado del precedente del repositorio: `tests/integration/test_suggest_perf.py` ya fija un presupuesto de 500 ms para el autocompletado de cuentas, que es la interacción comparable más exigente.

**Constraints**: ninguna escritura contable puede cambiar de comportamiento; la suite completa debe seguir verde (`2659 passed / 21 skipped` en SQLite y `2678 passed` en PostgreSQL antes de empezar); `ruff` y `mypy` limpios sobre 406 fuentes; `next build` verde; la constitution 1.0.1 es ley y sus cinco principios se verifican en puertas.

**Scale/Scope**: 103 pantallas existentes · 279 endpoints · 15 módulos RBAC · 6 superficies · 30 specs previas · 1 tabla nueva · 1 endpoint nuevo · 1 cabecera nueva · 5 consolidaciones de ruta

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

**Principio I · Partida doble** — **APPLICA PARCIALMENTE, sin conflicto**. La feature no crea ni modifica asientos: solo cuenta
entradas del diario para mostrarlas junto al ejercicio. La validación de balance MUST seguir exécutándose
en el backend en el punto más cercano a la persistencia, y esta feature no lo mueve. Puerta: la suite
completa sigue verde, incluido el trigger de balance diferido.

**Principio II · Inmutabilidad del diario** — **SIN CONFLICTO**. El diario se lee (recuento por ejercicio) y no se
escribe. La feature no añade ningún camino de `UPDATE` ni `DELETE` sobre `journal_entry`.

**Principio III · Multi-tenancy** — **APPLICA Y ES EL RIESGO PRINCIPAL DE ESTA FEATURE**. El principio exige que
toda consulta lleve el filtro explícito de la empresa activa. `X-Ejercicio-Activa` es un valor **recibido
del cliente** y por tanto no confiable, igual que lo es ya `X-Empresa-Activa`. Dos garantías lo hacen
legítimo, y ambas son requisitos de la feature, no de la constitution:

1. El ejercicio MUST validarse contra la empresa activa de la sesión. Un ejercicio que no pertenece a
   la empresa activa MUST rechazarse (FR-005). Esto convierte la cabecera en un **filtro interno del
   tenant**, no en una frontera de tenant.
2. `GET /api/v1/contexto` MUST filtrar por `empresa_id` derivado de la sesión, y el recuento de asientos
   por ejercicio MUST filtrar por `(empresa_id, ejercicio)`.

Verificación: pruebas de integración cross-empresa que demuestren que un ejercicio de la empresa B no se
resuelve en el contexto de la empresa A, y que `n_asientos` de la empresa A no incluye asientos de la B.
Esto es el Principio V(b) aplicado a esta feature.

**Principio IV · Correlatividad** — **NO APLICA**. La feature no emite números de asiento ni de factura.

**Principio V · Pruebas obligatorias** — **APPLICA**. V(b) es el núcleo de la feature (aislamiento
empresa/ejercicio) y tendrá pruebas de integración dedicadas. V(a) (balance estricto) no es un requisito
nuevo de esta feature porque no genera asientos, pero MUST verificarse como puerta de regresión sobre la
suite completa antes de cerrar cualquier tarea.

**Sección de stack · Audit logs** — **APPLICA Y ES OBLIGATORIO**. «registro obligatorio de cada operación de
escritura (usuario, timestamp UTC, IP, tipo de operación y delta/payload)» y MUST persistirse en la misma
transacción ACID. Marcar y desmarcar favoritos **son operaciones de escritura** y por tanto MUST auditarse
con `registrar_auditoria` dentro del boundary `get_db`. No es opcional ni aplazable a SPEC-032.

**Sección de stack · Transacciones** — **APLICA**. Los servicios de favoritos hacen `flush()` dentro del
boundary de `get_db` y MUST NOT abrir transacción propia, conforme a la enmienda 1.0.1.

**Sección de stack · Importes** — **NO APLICA**. La feature no maneja importes. `n_asientos` es un
contador entero, nunca un `Decimal` ni un `float`.

**Normas del frontend · Contexto de empresa** — **APLICA Y SE EXTIENDE**. La constitution exige que la sesión
mantenga el `empresa_id` activo y lo envíe en las cabeceras de cada petición. Esta feature extiende ese
mismo mecanismo a `ejercicio`, sin contradecirlo: la cabecera se envía siempre, se valida contra la
empresa de la sesión, y un cambio de empresa recalcula el contexto sin arrastrar datos (FR-004).

**Normas del frontend · Entrada contable optimizada** — **NO ES VIOLACIÓN, PERO SÍ RIESGO REAL Y CONCRETO.**
La constitution exige «usabilidad por teclado (teclas de acceso rápido, tabulación fluida y atajos)» para la
entrada de asientos. El ámbito literal de esa norma es la pantalla de entrada contable, que esta feature no
reconstruye. Pero un rail y un panel de destinos nuevos se interponen en el camino hacia esa pantalla: si
capturan `Tab`, `Enter` o las flechas, degradan un flujo que la constitution declara obligatorio. Además el
spec no contiene **ningún** requisito de teclado (0 de 29 FR), lo que `checklists/navegacion.md` ya
detectó en CHK029 y CHK031. Decisión: la navegación nueva MUST ser completamente operable por teclado y
MUST NOT capturar atajos que la pantalla de entrada contable ya use. Eso se recoge en research.md (D7).

**Governance** — No hay violación que justifique Complexity Tracking. No se requiere enmienda: lafeature es
coherente con la constitución 1.0.1 tal como está.

**Resultado del gate**: **PASS**. Dos requisitos de la constitution se convierten en restricciones
concretas del diseño (auditoría de favoritos y operabilidad por teclado sin secuestrar atajos), y ninguna
se relaja.

## Project Structure

### Documentation (this feature)

```text
specs/031-navegacion-superficies/
├── spec.md                 # Requisitos (ya existe)
├── plan.md                 # Este documento
├── research.md             # Phase 0: 7 decisiones resueltas
├── data-model.md           # Phase 1: favorito_usuario y el contexto de ejercicio
├── quickstart.md           # Phase 1: validación manual de los 6 recorridos
├── contracts/
│   ├── api-contracts.md    # GET /api/v1/contexto y endpoints de favoritos
│   └── navigation-contract.md  # Mapa de superficies, destinos y reglas de navegación
├── checklists/
│   ├── requirements.md     # Checklist built-in de /speckit.specify
│   └── navegacion.md       # Unit tests for requirements (40 ítems)
└── tasks.md                # Phase 2: /speckit.tasks (NO creado por /speckit.plan)
```

### Source Code (repository root)

Opción elegida: **web application** (backend + frontend en el mismo repositorio). No se añade raíz nueva.

```text
backend/
├── migrations/
│   └── 022_favoritos.sql          # NUEVO: tabla favorito_usuario
├── src/
│   ├── models/
│   │   └── navigation/
│   │       └── favorito.py            # NUEVO: FavoritoUsuario
│   ├── services/
│   │   ├── navigation/
│   │   │   ├── errores.py             # NUEVO: codigos de error (T005)
│   │   │   ├── contexto.py            # NUEVO: resuelve empresa + ejercicio + contadores
│   │   │   ├── ejercicio_activo.py    # NUEVO: valida X-Ejercicio-Activa contra la empresa
│   │   │   └── favoritos.py           # NUEVO: CRUD + auditoria + filtro por permiso
│   │   └── security/
│   │       └── catalogo.py            # MODIFICADO: evaluado y sin cambios (research D10)
│   ├── api/
│   │   ├── deps.py                    # MODIFICADO: get_ejercicio_activa
│   │   └── navigation.py              # NUEVO: /api/v1/contexto y /api/v1/favoritos
│   ├── db/
│   │   ├── migrate.py                 # MODIFICADO: ORDEN_PREFERENTE (022, 023)
│   │   └── triggers.py                # MODIFICADO: solo si el espejo SQLite lo pide
│   └── main.py                        # MODIFICADO: registra el router navigation
└── tests/
    ├── unit/
    │   ├── test_contexto_ejercicio.py # NUEVO
    │   ├── test_ejercicio_activo.py   # NUEVO
    │   ├── test_favoritos_servicio.py # NUEVO
    │   ├── test_favoritos_visibilidad.py   # NUEVO
    │   ├── test_favoritos_limite.py        # NUEVO
    │   ├── test_favoritos_reubicacion.py   # NUEVO
    │   ├── test_guard_mapa_superficies.py   # NUEVO
    │   ├── test_navegacion_invariantes.py   # NUEVO
    │   ├── test_navegacion_accesibilidad.py # NUEVO
    │   ├── test_rutas_consolidadas.py      # NUEVO
    │   └── test_constitucion_navegacion.py  # NUEVO
    ├── integration/
    │   ├── test_contexto_tenant_isolation.py # NUEVO: Principio V(b)
    │   ├── test_contexto_performance.py      # NUEVO: T069
    │   ├── test_ejercicio_tenant_isolation.py # NUEVO
    │   ├── test_favoritos_tenant.py           # NUEVO
    │   ├── test_navegacion_contratos.py       # NUEVO
    │   └── test_landings_resumen.py           # NUEVO
    ├── contract/
    │   └── test_contexto_api_contracts.py    # NUEVO
    └── unit/test_migrations.py                # MODIFICADO: ESPERADAS 022 y 023

frontend/
├── src/
│   ├── middleware.ts                  # NUEVO: guard de sesion optimista (T010)
│   ├── lib/
│   │   └── constantes-sesion.ts       # NUEVO: compartida con la ruta de sesion
│   ├── app/
│   │   ├── api/sesion/route.ts        # NUEVO: cookie httpOnly (solo servidor puede)
│   │   ├── contabilidad/page.tsx       # NUEVO: landing
│   │   ├── contabilidad/asientos/import-export/page.tsx  # NUEVO: canonica
│   │   ├── contabilidad/page.tsx       # landing (no redirect)
│   │   ├── facturacion/page.tsx        # NUEVO: landing
│   │   ├── informes/page.tsx           # NUEVO: landing
│   │   ├── fiscal/page.tsx             # NUEVO: landing
│   │   ├── maestros/page.tsx           # NUEVO: landing con empresas
│   │   ├── maestros/empresas/page.tsx  # NUEVO: listado (FR-028)
│   │   ├── layout.tsx                  # MODIFICADO: monta SessionGuard + AppShell
│   │   ├── page.tsx                    # MODIFICADO: deja de ser la lista de 24
│   │   ├── cierre/page.tsx             # ELIMINADO (redirect en next.config)
│   │   ├── cobros/page.tsx             # ELIMINADO
│   │   └── tesoreria/efe/page.tsx      # ELIMINADO
│   ├── components/navigation/
│   │   ├── surfaces.ts                 # NUEVO: mapa de las 6 superficies (T006)
│   │   ├── tipos.ts                    # NUEVO: contratos compartidos (T007)
│   │   ├── ejercicio.ts                # NUEVO: almacen por (empresa, ejercicio)
│   │   ├── SessionContext.tsx          # NUEVO: proveedor de contexto (T009)
│   │   ├── ContextZone.tsx             # NUEVO
│   │   ├── CompanySwitcher.tsx         # NUEVO
│   │   ├── ExerciseSwitcher.tsx        # NUEVO
│   │   ├── DestinationRail.tsx         # NUEVO
│   │   ├── SurfacePanel.tsx            # NUEVO
│   │   ├── FavoritesBar.tsx            # NUEVO
│   │   └── AppShell.tsx                # NUEVO
│   ├── services/client.ts             # MODIFICADO: cabecera de ejercicio + cookie
│   └── next.config.mjs                # MODIFICADO: 5 redirects
└── ...

**Structure Decision**: Se conserva la estructura existente de las 30 specs previas (backend + frontend) sin
introducir raíces nuevas. El backend nuevo vive en `models/navigation/`, `services/navigation/` y
`api/navigation.py`, siguiendo la convención de SPEC-030. El frontend nuevo vive en
`components/navigation/` con **una única fuente de verdad** (`surfaces.ts`) que el guard de mapa consume, de
modo que una pantalla sin asignar falla la suite en vez de quedar huérfana.

## Constitution Check · Re-evaluación posterior al diseño

*GATE: re-check after Phase 1 design. Ejecutado el 2026-09-27 tras generar research.md,
data-model.md, contracts/ y quickstart.md.*

| Principio | Veredicto inicial | Veredicto post-diseño | Cambio |
|---|---|---|---|
| I · Partida doble | parcial, sin conflicto | **igual** | Ninguno |
| II · Inmutabilidad del diario | sin conflicto | **igual** | Ninguno |
| III · Multi-tenancy | riesgo principal | **CONFIRMADO como riesgo gestionado** | El diseño añade dos garantias que el spec no exigia: FK compuesta `(empresa_id, usuario_id)` sobre `favorito_usuario`, que hace **inválido** un favorito sin vinculación del usuario a la empresa; y `n_asientos` filtrado por `empresa_id` de sesion **y** `estado='POSTED'`. Ver data-model §1 y §2 |
| IV · Correlatividad | no aplica | **igual** | Ninguno |
| V · Pruebas obligatorias | aplica (V(b) es el núcleo) | **igual, con 4 comprobaciones obligatorias** | quickstart las nombra: aislamiento de ejercicio, aislamiento de `n_asientos`, auditoría de favoritos en la misma transacción, cobertura del mapa de superficies |
| Audit logs | aplica y es obligatorio | **CONFIRMADO, con diseño concreto** | `FAVORITO_MARCAR` y `FAVORITO_DESMARCAR` con usuario, IP, UTC y payload dentro del boundary de `get_db`. research D9 |
| Transacciones | aplica | **igual** | `flush()` en el boundary; sin transacción propia |
| Importes | no aplica | **igual** | `n_asientos` es entero, nunca `Decimal` ni `float` |
| Frontend · contexto de empresa | aplica y se extiende | **igual** | La cabecera se envia siempre y se valida contra la empresa de la sesion |
| Frontend · entrada contable por teclado | riesgo real, no violación | **CONVERTIDO en requisito con prueba** | research D7 lo convierte en restriccion de diseño, y el recorrido R9 del quickstart lo verifica de forma observable: la navegacion no secuestra los atajos de la entrada contable |
| Governance | sin enmienda | **igual** | Ninguna |

**Resultado del gate post-diseño**: **PASS**. Ningun principio_relajado, ninguna enmienda
necesaria, y los dos puntos que podian haberlo hecho (contexto de cliente en cabecera y
escritura de favoritos) tienen diseno explicito que los hace conformes.

**Lo que el diseno revelo y el spec no pedia**: la constitution III resulto mas exigente que
el propio spec en el caso de los favoritos. El spec pedia «los favoritos son por usuario y por
empresa» (FR-022); el principio exige que `empresa_id` forme parte de **claves, indices y
filtros de toda operacion de datos**, y la unica forma de garantizarlo sin confiar en el
servicio es la FK compuesta. Es endurecimiento, no discrepancia.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

Ninguna entrada. El gate de la constitution pasa sin violaciones, con dos restricciones del constitution
convertidas en requisitos de diseño (auditoría de favoritos, operabilidad por teclado). No se requiere
enmienda.
