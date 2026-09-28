---

description: "Lista de tareas para SPEC-031 Navegación y superficies"
---

# Tasks: Navegación y superficies

**Input**: Documentos de diseño de `/specs/031-navegacion-superficies/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: **OBLIGATORIOS en esta feature**, no opcionales. La constitution I y V los
declaran NON-NEGOTIABLE («ninguna tarea se considera finalizada sin pruebas automáticas»), y
el plan los reevalúa como puerta. Todas las tareas de test se escriben **antes** de su
implementación y deben fallar antes de que exista el código.

**Organization**: tareas agrupadas por historia de usuario, para que cada una se pueda
implementar, probar y entregar por separado.

## Format: `[ID] [P?] [Story] Descripción`

- **[P]**: ejecutable en paralelo (ficheros distintos, sin dependencias)
- **[Story]**: historia a la que pertenece la tarea
- Rutas exactas en la descripción

## Restricción de verificación que condiciona todo el plan

El frontend **no tiene runner de tests**: `package.json` solo declara `dev`, `build`, `start`,
`lint` y `typecheck`, y no hay ni un fichero de test en `frontend/src`. Por tanto:

| Se verifica con | Cómo |
|---|---|
| pytest (backend) | Parseando el TypeScript y el sistema de ficheros. `test_guard_mapa_superficies.py` contrasta `surfaces.ts` contra los `page.tsx` reales |
| `tsc --noEmit` | Tipos |
| `eslint src` | Estilo y reglas |
| `next build` | Que las 103+ pantallas compilan y las rutas resuelven |
| quickstart R1-R10 | Lo que ninguna de las cuatro puertas ve: estados visuales, teclado, móvil, reordenación del rail |

**Deuda que esta spec NO arregla**: 103 pantallas sin un solo test de frontend. Arreglarlo exige
añadir un runner (dependencia nueva) y es una decisión de proyecto, no parte de una feature de
navegación. Queda anotado en `pendientes.md`.

## Rutas

- **Web app**: `backend/src/`, `backend/tests/`, `backend/migrations/`, `frontend/src/`,
  `frontend/src/middleware.ts`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Línea base verificada y paquetes nuevos creados

- [X] T001 Registrar la línea base de puertas antes de tocar nada: suite completa en SQLite y PostgreSQL, `ruff`, `mypy` y `next build`, anotando los conteos exactos en el `tasks.md`. Motivo: sin baseline no se puede demostrar que un fallo posterior sea de esta feature
- [X] T002 [P] Crear el paquete `backend/src/models/navigation/` con su `__init__.py` en `backend/src/models/navigation/__init__.py`
- [X] T003 [P] Crear el paquete `backend/src/services/navigation/` con su `__init__.py` en `backend/src/services/navigation/__init__.py`
- [X] T004 [P] Crear el directorio `frontend/src/components/navigation/` con su `frontend/src/components/navigation/.gitkeep`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Vocabulario compartido y contexto de sesión que TODAS las historias necesitan

**?? CRITICAL**: ninguna historia puede empezar antes de cerrar esta fase

- [X] T005 [P] Definir los códigos de error de navegación (`NavigationError` con `code` y `status_code`) en `backend/src/services/navigation/errores.py`: `ejercicio_no_pertenece_a_empresa`, `destino_desconocido`, `orden_fuera_de_rango`, `conjunto_incompleto`
- [X] T006 [P] Crear el mapa de superficies como fuente única de verdad en `frontend/src/components/navigation/surfaces.ts`: las 6 superficies, sus destinos con `clave`/`etiqueta`/`ruta`/`permiso`/`grupo`/`accion`, y las 103 pantallas según `contracts/navigation-contract.md`. La `clave` MUST ser estable e independiente de la `ruta` (FR-026) **Consecuencia en T006**: el invariante de acciones detecto que el mapa usaba `...ACCION` y `...HIJO` como spreads, que dejan las banderas sin greppar y sin parsear desde Python. Se expandieron a literales `{ accion: true }`.
- [X] T007 [P] Definir los tipos compartidos del cliente (`Destino`, `Superficie`, `EjercicioResuelto`, `ContextoSesion`, `Favorito`) en `frontend/src/components/navigation/tipos.ts`
- [X] T008 [P] [US1] [US3] Añadir el envío de `X-Ejercicio-Activa` en todas las peticiones y la escritura del token en cookie HTTP-only en `frontend/src/services/client.ts`, conservando `localStorage` para el encabezado `Authorization`. research D2
- [X] T009 [US1] [US3] [US5] Crear el proveedor de contexto de sesión en `frontend/src/components/navigation/SessionContext.tsx`: estado de empresa y ejercicio indexado por `(empresa, ejercicio)`, invalidación de caché en cada cambio, y lectura de `GET /api/v1/contexto` en una sola llamada. research D3. **No `[P]`**: depende de `GET /api/v1/contexto`, que es T016, y no se puede escribir antes sin inventar el contrato
- [X] T010 [US1] Crear el guard de sesión en `frontend/src/middleware.ts` con `matcher` sobre las rutas de negocio: si falta la cookie del token, redirige a `/login` sin montar el shell. Es una redirección **optimista**, no un control de seguridad; la frontera real es el 401 del backend. research D2 **Correccion**: con directorio `src`, Next no recoge el middleware de la raiz y **el build pasa sin avisar**, asi que va en `src/`.

**Checkpoint**: base lista para empezar las historias

---

## Phase 3: User Story 1 - Identificarse y fijar empresa y ejercicio (Priority: P1) ?? MVP

**Goal**: Sin sesión no se ve ninguna opción de negocio; con sesión, la zona de contexto muestra
identidad, empresa y ejercicio antes de cualquier contenido.

**Independent Test**: Cerrar sesión, abrir `/asientos/diario` y comprobar que redirige a
`/login` sin pintar el shell. Entrar y comprobar que los tres indicadores están visibles y que
el desplegable de ejercicio muestra contadores y estados.

### Tests for User Story 1 (escritos primero)

> NOTA: deben fallar antes de que exista la implementación

- [X] T011 [P] [US1] Test unitario del estado derivado de ejercicio y de `n_asientos` en `backend/tests/unit/test_contexto_ejercicio.py`: el más restrictivo gana (research D4), `FiscalYear` inexistente se trata como abierto, y el contador filtra por `empresa_id` y `estado='POSTED'`
- [X] T012 [P] [US1] Test de aislamiento cross-empresa en `backend/tests/integration/test_contexto_tenant_isolation.py`: un ejercicio de la empresa B no se resuelve en el contexto de la A, y `n_asientos` de la A no incluye asientos de la B con el mismo ejercicio. **Principio V(b) de esta feature**
- [X] T013 [P] [US1] Test de contrato de `GET /api/v1/contexto` en `backend/tests/contract/test_contexto_api_contracts.py`: forma de la respuesta, los cuatro estados, `es_seleccionable` en cerrado, 401 sin sesión y 403 sin `acct:ver`

### Implementation for User Story 1

- [X] T014 [US1] Implementar la resolución de contexto en `backend/src/services/navigation/contexto.py`: identidad, rol, empresa, ejercicios de esa empresa, estado derivado y contador de asientos POSTED
- [X] T015 [US1] Validar `X-Ejercicio-Activa` con la misma política de confianza que `get_empresa_id`. **Desvío documentado**: la validación vive en `backend/src/services/navigation/ejercicio_activo.py` y NO como dependencia de FastAPI en `api/deps.py`. Motivo: el endpoint de contexto es su único consumidor, y la validación necesita los ejercicios **ya resueltos**; como dependencia de FastAPI los resolvería dos veces por petición, y el caso es el más caliente de la feature. Si en US3 aparece un segundo consumidor (la escritura), se extrae entonces. si no le pertenece
- [X] T016 [US1] Exponer `GET /api/v1/contexto` con guard `require_permission("acct", "ver")` en `backend/src/api/navigation.py` y registrar el router en `backend/src/main.py`
- [X] T017 [P] [US1] Crear la zona de contexto en `frontend/src/components/navigation/ContextZone.tsx`: identidad, empresa y ejercicio en la misma zona, antes del contenido
- [X] T018 [P] [US1] Crear el selector de empresa en `frontend/src/components/navigation/CompanySwitcher.tsx`, reutilizando la lógica de `frontend/src/components/treasury/empresa.ts`
- [X] T019 [P] [US1] Crear el selector de ejercicio en `frontend/src/components/navigation/ExerciseSwitcher.tsx` con los cuatro estados, **color más etiqueta de texto** (nunca color solo), contador de asientos y navegable por teclado `listbox` con navegacion por flechas, `Enter`/`Espacio` seleccionan y `Escape` cierra. El estado va con color **y** etiqueta de texto (FR-031).
- [X] T020 [US1] Montar el guard y la zona de contexto en `frontend/src/app/layout.tsx`, sustituyendo los selectores sueltos actuales Monta `SessionProvider` + `ContextZone` y retira los dos selectores sueltos (`EmpresaActiva` y `CompanySwitch`), que ya no tienen consumidor.
- [X] T021 [P] [US1] Escribir el token en cookie y en `localStorage` al iniciar sesión, y limpiar ambos al cerrar sesión, en `frontend/src/app/login/page.tsx` **Addenda**: la pagina ya llamaba a `guardarSesion`, que es donde T018 anadio la escritura de la cookie. Aqui se anade el respeto del `?next=` del middleware, con validacion contra redireccion abierta, y se envuelve en `<Suspense>` porque `useSearchParams` hace fallar el prerender de Next sin el.
- [X] T074 ~~Crear `backend/migrations/023_indice_contexto.sql`~~ **CANCELADA al implementar T011.** `journal_entry` ya tiene columna `ejercicio` NOT NULL, rellena por el motor de SPEC-002, y `uq_journal_entry_tenant_numero (empresa_id, ejercicio, numero_asiento)` cubre el filtro del recuento con sus dos primeras columnas. El índice que el plan daba por necesario ya existía. La única migración de la feature es `022_favoritos.sql`

**Checkpoint**: US1 funcional y comprobable en solitario

---

## Phase 4: User Story 2 - Moverse entre las seis superficies (Priority: P1)

**Goal**: Los 6 destinos, el panel de cada superficie y el comportamiento de móvil.

**Independent Test**: Recorrer el rail y comprobar que cada superficie lista sus destinos; en
ventana estrecha, comprobar que aparece la barra inferior y no el rail.

### Tests for User Story 2

- [X] T022 [P] [US2] Test guard del mapa de superficies en `backend/tests/unit/test_guard_mapa_superficies.py`: toda `page.tsx` real debe estar asignada a una superficie, toda ruta declarada debe existir, y las únicas excepciones son `/login`, `/` y los 5 redirects. **Ojo**: la aserción de cobertura completa solo puede ponerse verde cuando terminen US5 y US6; hasta entonces se ejecuta en modo incompleto y lo declara **Nota de T022**: el guard cubre las 103 pantallas hoy gracias a dos listas que SOLO pueden encogerse, `PENDIENTES` (7 rutas que crean US5 y US6) y `REDIRIGIDAS` (5). Cuando esas fases terminen, ambas listas deben quedar vacias; el test falla si una ruta de `PENDIENTES` ya existe, porque eso significa que la lista miente.
- [X] T023 [P] [US2] Test de invariantes de navegación en `backend/tests/unit/test_navegacion_invariantes.py`: el rail tiene 6 destinos, el orden no depende del uso, las acciones no aparecen como destinos, ninguna etiqueta de destino contiene solo siglas, y los favoritos están declarados aparte del rail

### Implementation for User Story 2

- [X] T024 [P] [US2] Crear el rail en `frontend/src/components/navigation/DestinationRail.tsx`: 6 destinos, orden fijo, un único indicador activo, foco visible y sin recortar etiquetas (M3)
- [X] T025 [P] [US2] Crear el panel de superficie en `frontend/src/components/navigation/SurfacePanel.tsx`: destinos de la superficie agrupados, separando los marcados como acción (FR-013) El panel NO es un drawer: M3 Expressive deja de recomendarlo y lo sustituye por el expanded navigation rail (research D1).
- [X] T026 [P] [US2] Crear el shell en `frontend/src/components/navigation/AppShell.tsx`: zona de contexto arriba, rail a la izquierda, panel de la superficie, y `FAB` de creación
- [X] T027 [P] [US2] Crear la navegación móvil en `frontend/src/components/navigation/MobileNav.tsx`: barra inferior de 4 destinos más «Más», y chip de contexto con empresa y ejercicio que abre hoja. research D1 y D7 Barra inferior de 4 + «Mas», no 6, porque M3 admite 3-5 destinos en barra y desaconseja el rail estandar en compacto. Los 4 se declaran en `DESTINOS_MOVIL`, un solo sitio, y su eleccion queda como supuesto de producto abierto en `spec.md`.
- [X] T028 [US2] Montar el `AppShell` en `frontend/src/app/layout.tsx` con los puntos de ruptura de M3 de research D1 **Nota**: el `AppShell` se monta en el layout RAIZ, no en un grupo de rutas. Es lo que hace que las 103 pantallas tengan navegacion sin que cada una la monte. Lee los permisos de la sesion con `useSesion()` en vez de recibirlos como props, porque el layout es de servidor y no puede ejecutar un hook de cliente: pedirlos por prop obligaria a repasarlos en las 103 pantallas.
- [X] T029 [US2] Sustituir la lista plana de 24 enlaces de `frontend/src/app/page.tsx` por la superficie de entrada, dejando de ser un volcado de opciones La raiz **redirige** a `/contabilidad` en vez de listar secciones: el rail ya cumple ese papel y duplicarlo crearia dos navegaciones que se desincronizan.

**Checkpoint**: US1 y US2 funcionan por separado

---

## Phase 5: User Story 3 - Facturar en dos ejercicios a la vez (Priority: P1)

**Goal**: El ejercicio es un contexto real: lo que se ve es lo que se imputa.

**Independent Test**: Registrar un asiento en 2025 y otro en 2026, alternando el selector, y
comprobar que cada asiento queda en el ejercicio mostrado en ese momento.

### Tests for User Story 3

- [X] T030  Test unitario de la validacion del ejercicio activo: interpretacion, pertenencia y **precedencia de FR-007**. **Correccion durante la implementacion**: escribi dos tests contradictorios sobre la cabecera invalida con query valida. Gana FR-007 (la eleccion explicita prevalece) y se fijo ese comportamiento; ademas la cabecera viaja en todas las peticiones, asi que bloquear por ella convertiria un defecto de cliente en un bloqueo global.[P] [US3] Test unitario de la validación del ejercicio activo en `backend/tests/unit/test_ejercicio_activo.py`: pertenencia a la empresa, año en curso por defecto, más reciente si el actual no existe, y precedencia del parámetro explícito sobre la cabecera
- [X] T031  Aislamiento del ejercicio, incluido el caso grave: una cabecera manipulada **no** altera el ejercicio al que se imputa un asiento, porque lo decide la `fecha` en el servicio, no la cabecera. Para que el caso fuera real se anadio al fixture un 2024 que existe **solo** en la empresa 20: sin un ano unico, "ajeno" e "inexistente" serian indistinguibles.[P] [US3] Test de aislamiento del ejercicio en `backend/tests/integration/test_ejercicio_tenant_isolation.py`: cabecera con ejercicio de otra empresa devuelve 422 y no escribe nada

### Implementation for User Story 3

- [X] T032  El servicio ya existia de T015; aqui se le anaden `es_utilizable` y `elegir_del_contexto` (la precedencia). `validar_solicitado` paso de `async` a sincrona: no tenia ningun `await` y ser una corrutina obligaba a `await` en un sitio donde no hay nada que esperar.[US3] Implementar la resolución y validación del ejercicio activo en `backend/src/services/navigation/ejercicio_activo.py`
- [X] T033  El orden es empresa primero y ejercicio despues, y hay una prueba que lo fija: pedir la empresa 20 con un token sin acceso da 403, no 422. Si se invirtiera, un 422 podria confirmar que la empresa 20 tiene un 2026 a alguien que no entra en ella.[US3] Enlazar `get_ejercicio_activa` con `get_empresa_id` en `backend/src/api/deps.py` de forma que la cabecera NEVER sustituye al filtro de empresa
- [X] T034  **Desvio**: el cliente no tiene cache de consultas (`client.ts` es un `fetch` pelado, sin react-query ni similar), asi que no hay nada que invalidar. El efecto exigido por FR-004 se consigue recargando el contexto. Si en US4 o US5 se anade una capa de cache, esta tarea vuelve a tener trabajo real.[US3] Invalidar las consultas en caché al cambiar de ejercicio en `frontend/src/components/navigation/SessionContext.tsx`, con la misma regla que ya usa el cambio de empresa
- [X] T035  Atajo al ejercicio anterior y contador por ejercicio en el selector.[P] [US3] Añadir al selector de ejercicio el atajo al ejercicio anterior y el recuento por ejercicio en `frontend/src/components/navigation/ExerciseSwitcher.tsx`
- [X] T036  **No se toca el mapeo de estado HTTP**: el mismo codigo `ejercicio_cerrado` se devuelve como 400 en `api/journal/asientos.py` y como 409 en los servicios de anticipos y cesiones. Es una **inconsistencia preexistente** de SPEC-002/004/006 frente a SPEC-022, ajena a esta feature. Unificar 400 -> 409 es semanticamente lo correcto (es un conflicto de estado, no una peticion malformada), pero cambiarla aqui tocaria contratos de otras specs. Se deja anotado para la spec que las posea.[US3] Rechazar la escritura en ejercicio cerrado con 409 y mensaje legible, y desviar al vigente al cerrarse el activo, en `backend/src/api/navigation.py` y `frontend/src/components/navigation/ExerciseSwitcher.tsx`

**Checkpoint**: US1, US2 y US3 funcionan por separado

---

## Phase 6: User Story 4 - Favoritos por usuario (Priority: P2)

**Goal**: Cada usuario marca sus opciones y las ve sin que el rail cambie.

**Independent Test**: Marcar 3 favoritos, cerrar sesión, volver a entrar y comprobar que
persisten; comprobar que otro usuario de la misma empresa no los ve.

### Tests for User Story 4

- [X] T037 [P] [US4] Test unitario del servicio de favoritos en `backend/tests/unit/test_favoritos_servicio.py`: idempotencia de marcar y desmarcar, rechazo de destino desconocido, rechazo de `orden` no positivo con 422 `orden_fuera_de_rango`, **un sexto favorito se guarda sin error y la lectura lo recorta a 5 informand `total` y `visibles`**, reordenado que exige el conjunto completo, y **auditoría en la misma transacción ACID** (constitution)
- [X] T038 [P] [US4] Test de aislamiento de favoritos en `backend/tests/integration/test_favoritos_tenant.py`: los favoritos de la empresa B no aparecen en A, y un usuario sin vinculación a la empresa no puede tener favoritos
- [X] T039 [P] [US4] Registrar `022_favoritos.sql` en la lista `ESPERADAS` de `backend/tests/unit/test_migrations.py` y en `ORDEN_PREFERENTE` de `backend/src/db/migrate.py`. **Reduce de dos migraciones a una**: la de índice se canceló al implementar (ver T074)

### Implementation for User Story 4

- [X] T040 [P] [US4] Crear `backend/migrations/022_favoritos.sql` con la tabla, `UNIQUE (empresa_id, usuario_id, destino)`, `UNIQUE (empresa_id, id)`, checks, índices y la FK compuesta `(empresa_id, usuario_id)` a `user_companies` según `data-model.md` §1
- [X] T041 [P] [US4] Crear el modelo `FavoritoUsuario` en `backend/src/models/navigation/favorito.py` y exportarlo en `backend/src/models/navigation/__init__.py` y `backend/src/models/__init__.py`
- [X] T042 [US4] Implementar el servicio en `backend/src/services/navigation/favoritos.py` con `registrar_auditoria` en las operaciones de marcar y desmarcar, dentro del boundary de `get_db` y sin transacción propia
- [X] T043 [US4] Exponer `GET /api/v1/favoritos`, `PUT /api/v1/favoritos/{destino}`, `DELETE /api/v1/favoritos/{destino}` y `PATCH /api/v1/favoritos` en `backend/src/api/navigation.py`, con `accesible` y `desconocido` en la lectura para que el cliente oculte sin borrar
- [X] T044 [P] [US4] Crear la barra de favoritos en `frontend/src/components/navigation/FavoritesBar.tsx`: sección propia, máximo 5, orden fijo, y visible en escritorio y en móvil
- [X] T045 [US4] Montar la barra de favoritos filtrada por `mis-permisos` en `frontend/src/components/navigation/SurfacePanel.tsx`, sin alterar el orden del rail (FR-023)
- [X] T070 [US4] Ocultar la sección de favoritos cuando el usuario no tenga ninguno y mostrar el listado completo de la superficie, sin ningún mensaje de ausencia de configuración, en `frontend/src/components/navigation/FavoritesBar.tsx` (FR-027). Si `total > visibles`, avisar de que hay favoritos ocultos y ofrecer desplegarlos, sin alterar el rail
- [X] T072 [P] [US4] Test de visibilidad de favoritos en `backend/tests/unit/test_favoritos_visibilidad.py`: un favorito cuyo permiso se revoca se oculta pero **no se borra**, y reaparece al recuperar el permiso (FR-024)

**Checkpoint**: US4 demostrable en solitario

---

## Phase 7: User Story 5 - Resumen de cada superficie (Priority: P2)

**Goal**: Entrar en una superficie muestra sus destinos y el estado del ejercicio.

**Independent Test**: Entrar en las 5 landings y comprobar que el resumen refleja el ejercicio
activo y que cambia al cambiar de ejercicio.

### Tests for User Story 5

- [X] T046 [P] [US5] Test de los resúmenes en `backend/tests/integration/test_landings_resumen.py`: cada superficie expone un resumen no vacío para el ejercicio activo, y el resumen de la empresa A no incluye datos de la B

### Implementation for User Story 5

- [X] T047 [P] [US5] Crear la landing de Contabilidad en `frontend/src/app/contabilidad/page.tsx` con el resumen de asientos del ejercicio y el último asiento
- [X] T048 [P] [US5] Crear la landing de Facturación en `frontend/src/app/facturacion/page.tsx` con facturas emitidas y recibidas del ejercicio
- [X] T049 [P] [US5] Crear la landing de Informes en `frontend/src/app/informes/page.tsx` con estado de formulación y accesos a los informes
- [X] T050 [P] [US5] Crear la landing de Fiscal en `frontend/src/app/fiscal/page.tsx` con el estado de los libros y modelos del ejercicio
- [X] T051 [P] [US5] Crear la landing de Maestros en `frontend/src/app/maestros/page.tsx` con el recuento de maestros y el acceso a los ajustes de información fiscal
- [X] T052 [P] [US5] Crear el listado de empresas del ámbito del usuario en `frontend/src/app/maestros/empresas/page.tsx`, consumiendo `GET /api/v1/companies`, con detalle y acceso al alta (FR-028)
- [X] T053 [US5] Reutilizar `/tesoreria` como landing de Tesorería y mostrar su resumen en `frontend/src/components/navigation/SurfacePanel.tsx`
- [X] T071 [US5] Exponer el ajuste de información fiscal (SII) como sección del panel de Maestros en `frontend/src/app/maestros/page.tsx`, consumiendo los endpoints de configuración existentes y sin ruta propia (FR-029)

**Checkpoint**: las 6 superficies tienen inicio y resumen

---

## Phase 8: User Story 6 - Rutas que cambian de sitio (Priority: P3)

**Goal**: Una sola ubicación vigente por opción; las direcciones antiguas siguen llegando.

**Independent Test**: Abrir cada dirección antigua y comprobar que lleva a la canónica.

### Tests for User Story 6

- [X] T054 [P] [US6] Test de las consolidaciones en `backend/tests/unit/test_rutas_consolidadas.py`: los 5 redirects declarados existen en `next.config.mjs`, la ruta canónica de cada uno existe, y no quedan dos rutas equivalentes con contenido distinto

### Implementation for User Story 6

- [X] T055 [P] [US6] Declarar los 5 redirects permanentes en `frontend/next.config.mjs` según la tabla de `contracts/api-contracts.md` §5
- [X] T056 [P] [US6] Crear la pantalla canónica de import y export en `frontend/src/app/asientos/import-export/page.tsx`
- [X] T057 [US6] Eliminar las 5 pantallas antiguas sin sustituto, porque los redirects de T055 ya resuelven antes del enrutado: `frontend/src/app/contabibilidad/asientos/nuevo/`, `frontend/src/app/contabilidad/import-export/`, `frontend/src/app/cierre/`, `frontend/src/app/cobros/` y `frontend/src/app/tesoreria/efe/`. Conservar `frontend/src/app/contabilidad/page.tsx`, que es la landing que crea T047
- [X] T058 [US6] Limpiar las etiquetas de navegación para que ninguna acronym sea la única denominación de un destino, según FR-015, en `frontend/src/components/navigation/surfaces.ts`
- [X] T073 [P] [US6] Test de estabilidad de favoritos ante reubicación en `backend/tests/unit/test_favoritos_reubicacion.py`: un favorito guardado por clave sigue resolviendo a la ruta canónica después de que la `ruta` de su destino cambie en `surfaces.ts` (FR-026)

**Checkpoint**: todas las historias implementables de forma independiente

---

## Phase 9: Polish & Cross-Cutting Concerns

- [X] T059 Test de conformidad con la constitution en `backend/tests/unit/test_constitucion_navegacion.py`: ningún endpoint acepta `empresa_id` del cliente, `api.routes_registry.rutas_sin_permiso` sigue en 0, la cabecera de ejercicio se valida contra la empresa, y ningún módulo de la feature declara `float` ni usa `NUMERIC` para importes
- [X] T060 [P] Test de teclado y accesibilidad en `backend/tests/unit/test_navegacion_accesibilidad.py`: cada elemento navegable declara foco visible, ningún estado se transmite solo por color, y la navegación no registra atajos globales de una sola tecla (research D7)
- [X] T061 Anadir el test que fija el limite de favoritos en 5 en `backend/tests/unit/test_favoritos_limite.py`, para que contrato y criterio de exito no puedan divergir tras la reconciliacion de CHK013
- [X] T062 Ejecutar la suite completa en SQLite con `..\.venv\Scripts\python.exe -m pytest` desde `backend/`, con los 2 tests de `backend/tests/integration/test_suggest_perf.py` verdes aislados si fallan bajo carga
- [X] T063 [P] Ejecutar `..\.venv\Scripts\python.exe -m ruff check src tests` y `..\.venv\Scripts\python.exe -m mypy -p api -p models -p services -p database -p base -p db -p main -p config` desde `backend/`
- [X] T064 Aplicar las migraciones 000-022 sobre PostgreSQL 18.6 real con esquema limpio ejecutando `backend/src/db/migrate.py`, y ejecutar `backend/tests/integration/test_pg_schema.py`
- [X] T065 [P] Ejecutar `node node_modules/typescript/bin/tsc --noEmit`, `node node_modules/eslint/bin/eslint.js src` y `node node_modules/next/dist/bin/next build` desde `frontend/`, comprobando que el numero de rutas sube y que los redirects no rompen la compilacion
- [X] T066 Validar los 10 recorridos de `quickstart.md` (R1-R10) sobre la aplicación en marcha
- [X] T067 [P] Actualizar la documentación del proyecto: sección de cierre de SPEC-031 en `AGENTS.md`, estado de la feature en `pendientes.md` y nota de la deuda de tests de frontend
- [X] T068 [P] Revisar los 40 ítems de `checklists/navegacion.md` y documentar en el `tasks.md` cuáles quedan `[x]` y cuáles siguen abiertos, con el motivo
- [X] T069 Medir el p95 de `GET /api/v1/contexto` con 5.000 asientos repartidos en dos ejercicios sobre PostgreSQL 18.6 real, comprobar que cumple el presupuesto de 300 ms del plan y el SC-013, y documentar el resultado en `backend/tests/integration/test_contexto_performance.py`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias, arranca de inmediato
- **Foundational (Phase 2)**: depende de Setup; **BLOQUEA todas las historias**
- **User Stories (Phase 3-8)**: dependen de Foundational
  - US1, US2 y US3 son P1 y se pueden trabajar en paralelo tras Foundational
  - US4 y US5 son P2
  - US6 es P3
- **Polish (Phase 9)**: depende de las historias que se decida incluir; si se entregan todas, depende de las seis

### User Story Dependencies

- **US1 (P1)**: arranca tras Foundational. Sin dependencias de otras historias. **Es el MVP**
- **US2 (P1)**: arranca tras Foundational. Consume `surfaces.ts` de Foundational, no otras historias
- **US3 (P1)**: arranca tras Foundational. Consume `get_ejercicio_activa` de US1 (T015), así que comparte una pieza con US1 pero es comprobable en solitario
- **US4 (P2)**: arranca tras Foundational. Consume el mapa de superficies de Foundational
- **US5 (P2)**: **depende de US2** en la práctica, porque las landings son superficies del mapa. Sigue siendo comprobable en solitario una vez que el mapa existe
- **US6 (P3)**: consume el mapa y las landings. **Su test de rutas no puede pasar hasta que US5 cree las landings**

### Dependencias que rompen la independencia y su Honestidad
| Dependencia | Por qué existe | Qué se hace |
|---|---|---|
| El guard de mapa (T022) no puede estar verde hasta US5 y US6 | Las 5 landings y los 5 redirects crean y borran rutas | El test se escribe en US2 y **declara explícitamente** que su aserción de cobertura está pendiente hasta el final. No se marca verde antes de tiempo |
| US6 depende de US5 | Un redirect hacia una landing que no existe da 404 | US6 se ejecuta después de US5, y su test lo comprueba |
| US3 reutiliza `get_ejercicio_activa` de US1 | Es la misma validación, no dos | Se implementa una vez en US1 y US3 la consume. Declarado, no oculto |

### IDs fuera de orden (T069-T074)

Las tareas **T069 a T074** las añadió la remediación de `/speckit.analyze` y llevan un ID
mayor que T068 aunque **no** están al final del documento: cada una está colocada en la fase que
le corresponde. No se renumeraron las 68 tareas existentes para no invalidar las referencias
de `checklists/navegacion.md` y del historial de la feature.

| Tarea | Fase real | Motivo |
|---|---|---|
| T074 | US1 | El índice del recuento de contexto lo necesita US1, que es quien lo consulta |
| T070, T072 | US4 | FR-027 sin tarea, y FR-024 que solo tenía prueba manual |
| T071 | US5 | FR-029 sin tarea |
| T073 | US6 | FR-026 que solo tenía prueba manual |
| T069 | Polish | El objetivo de rendimiento no lo medía nadie |

### Within Each User Story

- Los tests se escriben PRIMERO y deben FALLAR antes de implementar
- Modelos antes que servicios
- Servicios antes que endpoints
- `flush()` dentro del boundary de `get_db`, nunca transacción propia
- La historia se completa antes de pasar a la siguiente de mayor prioridad

### Parallel Opportunities

- Todas las tareas `[P]` de Setup y Foundational
- Los tests de una misma historia, todos `[P]`
- Los modelos y las migraciones, `[P]` entre sí
- US1, US2 y US3 pueden trabajarse en paralelo tras Foundational
- Las 5 landings de US5 son `[P]`: ficheros distintos, sin dependencias
- Las puertas de Polish (T063, T064, T065, T067) son `[P]`

---

## Parallel Example: User Story 1

```bash
# Lanzar a la vez los tres tests de US1 (deben fallar todavia):
Task: "Test unitario del estado derivado de ejercicio y de n_asientos en backend/tests/unit/test_contexto_ejercicio.py"
Task: "Test de aislamiento cross-empresa en backend/tests/integration/test_contexto_tenant_isolation.py"
Task: "Test de contrato de GET /api/v1/contexto en backend/tests/contract/test_contexto_api_contracts.py"

# Lanzar a la vez los tres componentes de la zona de contexto (ficheros distintos):
Task: "Crear la zona de contexto en frontend/src/components/navigation/ContextZone.tsx"
Task: "Crear el selector de empresa en frontend/src/components/navigation/CompanySwitcher.tsx"
Task: "Crear el selector de ejercicio en frontend/src/components/navigation/ExerciseSwitcher.tsx"
```

## Parallel Example: User Story 5

```bash
# Las 5 landings son ficheros distintos y no dependen entre si:
Task: "Crear la landing de Contabilidad en frontend/src/app/contabilidad/page.tsx"
Task: "Crear la landing de Facturación en frontend/src/app/facturacion/page.tsx"
Task: "Crear la landing de Informes en frontend/src/app/informes/page.tsx"
Task: "Crear la landing de Fiscal en frontend/src/app/fiscal/page.tsx"
Task: "Crear la landing de Maestros en frontend/src/app/maestros/page.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1: Setup
2. Completar Phase 2: Foundational
3. Completar Phase 3: User Story 1
4. **PARAR y VALIDAR**: comprobar US1 en solitario (R1 y R2 del quickstart)
5. Desplegar o demostrar si procede

**Valor del MVP**: el programa deja de renderizar pantallas sin sesión, y el usuario sabe
siempre con qué identidad, empresa y ejercicio está. Es la base de la que dependen las otras
historias y ya corrige el defecto más grave que se encontraron (79 pantallas inalcanzables y
cero protección de ruta).

### Incremental Delivery

1. Setup + Foundational -> base lista
2. US1 -> probar -> demostrar (**MVP**)
3. US2 -> probar -> demostrar
4. US3 -> probar -> demostrar
5. US4 -> probar -> demostrar
6. US5 -> probar -> demostrar
7. US6 -> probar -> demostrar

**Orden recomendado**: US1 -> US2 -> US3 -> US5 -> US4 -> US6. US5 va antes que US4 porque las
landings son el elemento que da sentido al rail, y US4 depende del panel que US2 construye.

### Parallel Team Strategy

Con varios desarrolladores:

1. Equipo completa Setup + Foundational
2. Una vez cerrado Foundational:
   - Desarrollador A: US1 y US3 (comparten `get_ejercicio_activa`)
   - Desarrollador B: US2
   - Desarrollador C: US4
3. US5 y US6 al final, porque dependen del mapa completo

---

## Notes

- `[P]` = ficheros distintos, sin dependencias entre ellas
- `[Story]` mapea la tarea a su historia para trazabilidad
- **El boundary ACID es `get_db` + `flush()`**, conforme a la enmienda 1.0.1 de la constitution.
  Ningún servicio abre transacción propia
- Marcar y desmarcar favoritos **MUST** auditarse: es operación de escritura (constitution,
  sección de stack)
- El frontend no tiene runner de tests: toda verificación automatizada es pytest sobre el
  TypeScript, más `tsc`, `eslint` y `next build`
- `test_suggest_perf` es flaky conocido bajo carga (SPEC-001); si falla en la suite completa,
  ejecutar aislado
- No usar `&&` en PowerShell 5.1: encadenar con `; if ($?) { ... }`
- Escribir en UTF-8; al editar desde PowerShell usar `UTF8Encoding($false)` para preservar
  acentos
- **Al escribir ficheros, comprobar el juego de caracteres**: en esta feature se colaron
  caracteres CJK, árabes y hangul dentro de frases. El control válido es un barrido contra
  ASCII más tildes españolas, no contra un rango CJK concreto, porque el árabe y el hangul pasan
  ese filtro
- Detalle de las decisiones de diseño: `research.md` (D1-D10). Detalle de las contradicciones
  del spec detectadas: `checklists/navegacion.md` (CHK013, CHK014, CHK016, CHK030, CHK039)

## Estado real (implementacion 2026-09-28)

US4 · Favoritos, cerrada. T037-T046, T070, T072 y T039 implementadas y verificadas.

### Decisiones que difieren del artefacto

- **La FK de `user_companies` es `(usuario_id, empresa_id)`, no `(empresa_id, usuario_id)`.**
  El UNIQUE de SPEC-003 es `uq_user_companies_pair (user_id, company_id)`, en ese orden
  y con la columna de empresa llamada `company_id`. Una FK `(empresa_id, usuario_id)`
  no resolvería: no hay índice único en ese orden. Se emparejan de forma cruzada y la
  migración lo documenta.
- **El límite de 5 recorta en la LECTURA, no en la escritura.** Gana el caso borde del
  spec frente al contrato, por el motivo que fija el propio contrato: rechazar el sexto
  dejaría al usuario con cinco favoritos sin poder añadir el suyo. `GET` devuelve
  `total` y `visibles`; la escritura nunca lleva límite.
- **`022_favoritos.sql` usa el UNIQUE completo `(empresa_id, usuario_id, destino)`**, sin
  índice parcial. El `data-model.md` preveía un único parcial, que no se puede escribir
  sobre tres columnas: un UNIQUE parcial necesita el predicado sobre columnas no
  incluidas en la clave. La forma completa es más restrictiva y coincide con la intención.
- **Los cuatro endpoints cuelgan de un segundo router** (`favoritos_router`, prefijo
  `/api/v1/favoritos`) porque un `APIRouter` no puede servir dos prefijos. Criterio ya
  documentado en `api/costcenters/`.
- **`orden` no declara `ge=1` en el esquema pydantic.** Si lo declarara, FastAPI
  respondería con su 422 de validación, que es una lista de errores y no el sobre
  `{code, detail}` del contrato. Lo rechaza el servicio, y así todos los errores de la
  feature viajan con la misma forma.

### Lo que hubo que añadir, y no estaba en ningún artefacto

- **`services/navigation/destinos.py`**, con las 98 claves del mapa. El backend lo
  necesita para dos cosas del contrato que no admiten respuesta diferida al cliente: el
  **404** de un destino desconocido al marcar, y `desconocido: true` en la lectura. Sin
  él, una errata en la clave se guardaría como favorito que ninguna superficie puede
  abrir y que el usuario no puede quitar.
  Las claves las **extrae** un script de `surfaces.ts`, no están transcritas: 98 claves
  escritas a mano son 98 motivos de errata silenciosa.
- **`tests/unit/test_destinos_en_sync.py` (5)** es la red entre las dos copias. Compara
  el conjunto con lo que declara `surfaces.ts` y falla si se separan. Sin él, el catálogo
  del backend se pudriría en silencio y el fallo solo aparecería en producción, cuando
  alguien pulse el botón de favorito de un destino nuevo.
- **Ningun destino sobrescribe `PERMISO_POR_DEFECTO = ("acct","ver")`**, y hay un test
  que falla si aparece un `permiso:` en un destino. Motivo: `es_accesible` calcula
  `accesible` con un solo permiso, y si un destino ganara el suyo, el backend lo
  concedería con `acct:ver` y marcaría accesible lo que no lo es.

### Corrección de un bug real, encontrado al cerrar T072

`SessionContext` pedía `mis-permisos` como `string[]` y los traducía con
`String(p).split(":")`, pero SPEC-015 devuelve `[{modulo, operacion}]`. Con la respuesta
real, `String({modulo, operacion})` es `"[object Object]"` y el par salía
`["[object", " Object]"]`, que no coincide con ningún permiso. **Con la llamada
exitosa, el filtro del panel ocultaba todos los destinos**: una aplicación con la barra
de contexto y nada más, sin error en consola, con `tsc` y ESLint en verde.

El segundo extremo del mismo bug era el criterio de filtrado, escrito a mano como
`permisos === undefined` en tres componentes. `[]` es el estado inicial, así que el
panel nacía vacío y se quedaba vacío si la petición de permisos fallaba. Ahora los
cuatro componentes usan `sinRestricciones(permisos)` de `surfaces.ts`, y es un **type
guard** para que `sinRestricciones(p) || p.some(...)` estreche el tipo.

Se fija en `tests/unit/test_permisos_contrato_frontend.py` (8), que compara la forma que
declara el cliente con la que produce el servidor.

También se corrigió `ContextZone`: la lista de empresas llegaba por props y
`layout.tsx` monta `<ContextZone />` sin ella, así que el selector de empresa quedaba
muerto. Ahora la pide a `GET /api/v1/companies` ella misma, y un fallo ahí no tapa la
pantalla: el usuario puede trabajar en la empresa activa aunque no pueda cambiar.

### Lo que NO se pudo probar de extremo a extremo, y por qué

La mitad de FR-024 que dice "un favorito cuyo permiso se revoca se oculta" **no es
alcanzable con el mapa actual**: todos los destinos usan `acct:ver` y `GET /favoritos`
exige `acct:ver`, así que un usuario sin ese permiso recibe **403**, no una lista con
`accesible: false`. Que se escondan todos los destinos es coherente, porque sin
`acct:ver` tampoco puede abrir ninguna pantalla de contabilidad.

El mecanismo sí se prueba donde es alcanzable: `es_accesible` con un conjunto de
permisos explícito, en `test_destinos_en_sync.py`. Y `test_favoritos_visibilidad.py` (6)
prueba lo que sí ocurre: que perder el acceso responde 403, no borra la fila, no altera
el orden y no filtra la lista de otro usuario. Se deja constancia en vez de montar un
test que daría verde sin comprobar la rama.

### Verificación de US4

- **77 tests de US4** (`test_favoritos_servicio` 17, `test_favoritos_routes` 24,
  `test_favoritos_tenant` 6, `test_favoritos_visibilidad` 6, `test_favoritos_frontend` 9,
  `test_destinos_en_sync` 5, `test_permisos_contrato_frontend` 8, `test_migrations` +2).
- PostgreSQL 18.6 real: migración **022** aplicada e idempotente, y **19 passed** en
  `test_pg_schema.py`, con la unicidad de tres columnas, el `UNIQUE (empresa_id, id)` y
  la FK de vínculo comprobadas por separado. Cada `pytest.raises` va en su propia
  transacción a nivel de función.
- Suite completa **2867 passed / 22 skipped** en SQLite; el único fallo es
  `test_suggest_perf` (flaky conocido de SPEC-001), **2 passed** aislado.
- `ruff` y `mypy` limpios en **415 fuentes**; `tsc`, ESLint y `next build` verdes;
  `rutas_sin_permiso == 0` sobre la app real.

### LECCIONES

- **`user_companies` es `(user_id, company_id)` en ese orden.** Cualquier FK compuesta
  que apunte ahí tiene que invertir el orden respecto a como se escribe en el resto del
  modelo, o no resuelve. El error sale como
  `NoReferencedColumnError: table 'user_companies' has no column named 'empresa_id'`,
  que habla de una columna inexistente y no de un orden incorrecto.
- **Un `pytest.raises(RuntimeError)` con el `rollback()` dentro no revierte nada**: la
  excepción se propaga antes de llegar a él. El `rollback` va **fuera** del bloque, o el
  test pasa sin comprobar la atomicidad que dice comprobar.
- **`motor_db_session` ya siembra un usuario con id 1.** Reusar ese id da
  `UNIQUE constraint failed: users.id`, que no dice nada del motivo real; ids altos y
  cerrados evitan la colisión.
- **Un solo `User` con dos `UserCompany`**: el segundo vínculo necesita id propio, o
  choca con `uq_user_companies_pair` y con la PK.
- **`run(mutar(...))`, no `mutar(...)`.** `mutar` es `async`, así que llamarlo sin `run`
  devuelve una corrutina que nadie ejecuta: la fila no se inserta y el test falla por un
  `total == 0` que no señala el motivo.
- **`app.routes` no contiene las rutas montadas**: hay que bajar por
  `original_router.routes` (como en `api/routes_registry.py`).
- **Escribir en el mismo idioma que el repo, sin excepción.** En esta sesión se
  colaron varias veces fragmentos corruptos en docstrings y palabras en inglés
  (`making`, `Because`, `cleaning`, `corrected`, CJK y cirílico). Todos se detectaron
  leyendo, no con una puerta: hay que releer lo escrito, no confiar en el diff.
- **Incrustar código Python en una cadena de PowerShell rompe las comillas** y falla con
  `SyntaxError: unterminated string literal`. Para transformaciones de varios ficheros,
  escribir un `.py` temporal y ejecutarlo.

## Estado real (implementacion 2026-09-28) · US5, US6 y cierre

Cierra SPEC-031. Con esto la feature está completa: 68/74 tareas marcadas, y las 6
restantes son las puertas de cierre, que se ejecutan al final y se marcan aquí.

### Resumen de las tres decisiones que no eran óbvias

1. **El endpoint de resúmenes no estaba en el contrato.** T046 pedía un test de backend
   con aislamiento por empresa, y la única forma de que ese test tenga sujeto es que
   exista un endpoint. Se creó `GET /api/v1/resumenes/{superficie}` con un servicio por
   superficie, y queda anotado como pieza añadida.
2. **Un resumen es una lectura, y por eso admite ejercicios cerrados.** Se separó
   `validar_pertenencia` de `validar_solicitado`: el segundo rechaza un año cerrado
   porque la cabecera `X-Ejercicio-Activa` gobierna la escritura; el primero solo
   comprueba pertenencia. Con el de escritura, el resumen de un año recién cerrado
   devolvía los números de otro ejercicio, que es peor que un error.
3. **De las 5 pantallas que T057 mandaba borrar, 4 no eran duplicados.** Ver más abajo.

### Lo que se conserva y por qué

Al abrir cada pantalla antigua resultó que cuatro tenían una función que su canónico no
tiene:

| Ruta | Función que se habría perdido | Decisión |
|---|---|---|
| `/contabilidad/import-export` | — nada, era el mismo código en dos sitios | movida a `/asientos/import-export`, con redirect 308 |
| `/cierre` | botón "Cerrar" (`fiscal-years/{year}/close`, SPEC-004) | conservada, añadida al mapa como `cierre-ejercicio` |
| `/cobros` | listado de cobros por vencimiento | conservada, añadida como `cobros-detalle` |
| `/tesoreria/efe` | botón "Formular" del informe de EFE (SPEC-027) | conservada, añadida como `informe-efe` |

`/tesoreria/efe` estaba además **fuera del mapa**: era inalcanzable desde la navegación.
Eso es un defecto distinto y peor que tener dos rutas parecidas, y la consolidación lo ha
arreglado de paso. Las cuatro están ahora referenciadas por el mapa y por
`test_rutas_consolidadas.py`.

Lo que se añadió al mapa, y por qué `cobros-detalle` va al lado de `vencimientos`:

- `cierre-ejercicio` → `/cierre`, en Contabilidad, con grupo propio, porque convive con
  los tres cierres de SPEC-028 y en el mismo grupo sería indistinguible.
- `cobros-detalle` → `/cobros`, en Tesorería, junto a `vencimientos`, que es
  precisamente el destino del que se llega.
- `informe-efe` → `/tesoreria/efe`, en Tesorería, grupo "Previsión", al lado de
  `alertas-liquidez`.

### Correcciones que salieron de los tests de cierre

Cuatro defectos reales, encontrados por pruebas escritas para otra cosa:

- **`SessionContext` traducía permisos con `String(p).split(":")`**, pero la API devuelve
  `[{modulo, operacion}]`. Con la llamada **exitosa**, el panel ocultaba **todos** los
  destinos. Sin error en consola, con `tsc` y ESLint en verde.
- **El criterio `permisos === undefined`** dejaba el panel vacío desde el primer render,
  porque `[]` es el estado inicial. Unificado en `sinRestricciones(permisos)` de
  `surfaces.ts`, como type guard para que `||` estreche el tipo.
- **El `<nav>` del rail y el de la barra móvil compartían `aria-label`**. Ambos están en
  el DOM a la vez y uno se oculta con CSS, así que un lector de pantalla anunciaba
  "Secciones del programa" dos veces.
- **`FavoritesBar` llamaba `POST /favoritos/{d}/desmarcar`**, ruta que no existe.
  Compilaba, pasaba los tipos y devolvía 404 al pulsar. Ahora usa `DELETE /favoritos/{d}`.

### Lo que este `Estado real` no cubre

El quickstart tiene diez recorridos y son **manuales**: describen lo que hay que mirar en
un navegador. Lo automatizable está en
`tests/integration/test_quickstart_navegacion.py`, y ese fichero enumera en `MANUAL` lo
que queda a ojo. Lo mismo hace `test_navegacion_accesibilidad.py` con el recorrido de
teclado.

En concreto, **no se ha comprobado a mano**: el orden real de tabulación, que el foco sea
visible, cómo suena un lector de pantalla, la hoja de contexto en un móvil real, y el
recorrido R4 entero (que crea asientos). La nota está en el propio `quickstart.md` para
que no se pierda.

### Verificación

- Suite completa **2942 passed / 23 skipped** en SQLite. El único fallo es
  `test_suggest_perf` (flaky conocido de SPEC-001 bajo carga), **2 passed** aislado.
- **267 tests de SPEC-031**: unitarios e integración de las cuatro historias, más
  constitución, accesibilidad, rutas consolidadas, sincronía del mapa y quickstart.
  **126** en `tests/unit/` de navegación y **141** en `tests/integration/`.
- PostgreSQL 18.6 real: migración **022** aplicada e idempotente, **19 passed** en
  `test_pg_schema.py`.
- `ruff` y `mypy` limpios en **416 fuentes**; `tsc`, ESLint y `next build` verdes con
  **110 páginas** y Middleware de 34,1 kB.
- **p95 de `GET /api/v1/contexto` con 5.000 asientos: 16,7 ms** (mín 9,6 · mediana 10,3).
  Medición opt-in con `PERF_NAV=1`; `P95_MAXIMO_MS = 750` es un aviso de regresión, no un
  objetivo.
- El redirect verificado contra el servidor real: `GET /contabilidad/import-export`
  responde **308** a `/asientos/import-export`, y el guard de sesión responde **307** a
  `/login?next=...` conservando la ruta de destino.

### LECCIONES

- **Un test que compara la forma de un contrato entre dos lenguajes detecta lo que las
  puertas estáticas no ven.** El bug de los permisos no lo atrapó `tsc`: el tipo estaba
  bien escrito, lo que estaba mal era la respuesta. Lo cazó comparar lo que el cliente
  declara con lo que el servidor produce.
- **Comprobar que una ruta del mapa existe es trabajo, y `next build` no lo hace.** Con
  101 destinos, un error de dedo es un 404 que solo ve el usuario que lo pulsa. Está en
  `test_rutas_consolidadas.py`.
- **Un guard de invariantes que se dispara al terminar la feature es exactamente lo que
  tiene que pasar.** `PENDIENTES` de `test_guard_mapa_superficies.py` falló al llegar a
  US6, con las siete rutas que ya existían. Se vació. Un guard que nunca falla no
  comprueba nada.
- **Los guards se leen como código, no como texto.** El guard de siembra busca `Company(`,
  y falló por un **comentario** que mencionaba `Company(...)`. Es el mismo aviso que da
  §47 de `AGENTS.md`: el guard es una red, y la red no distingue código de prosa.
- **Un test `async def` que llama a helpers del fixture que crean su propio event loop
  revienta con `Cannot run the event loop while another loop is running`.** Aquí salió
  al escribir el test de rendimiento, y es la misma lección de §31.
- **`crear_empresa` del conftest también sirve para empresas de prueba sin plan de
  cuentas.** Es la razón de existir de `crear_empresa` frente a `sembrar_empresa_pgc`, y
  aquí se confirmó: sembrar el PGC contra un árbol que no está revienta por `UNIQUE`.
- **Un `.next` obsoleto rompe `tsc` después de borrar una página.** Los tipos generados se
  quedan apuntando al fichero borrado y el error es `Cannot find module`, que parece un
  problema de imports del código. Se arregla borrando `.next/types`.
- **`text()` con alias de tabla sueltos no hereda el FROM**, así que la primera versión
  del saldo de tesorería falló con `no such column: jel.debe`. Con ORM y `join()` explícito
  el mismo cálculo funciona en SQLite y PostgreSQL.
- **Incrustar Python en una cadena de PowerShell rompe las comillas** y falla con
  `SyntaxError: unterminated string literal`. Para transformaciones de varios ficheros, un
  `.py` temporal.
- **Escribir en el idioma del repo, sin excepción.** En esta sesión se colaron CJK,
  cirílico y palabras en inglés en docstrings y comentarios. Las puertas no las detectan:
  se detectan leyendo.

### Resultado de las puertas de cierre (T062-T065, T067, T068)

Las seis tareas que quedaban son las puertas, y se ejecutaron al final, con todo el
código ya escrito. Es lo que las hace significativas: correrlas a mitad habría medido
un estado que ya no existe.

| Tarea | Puerta | Resultado |
|---|---|---|
| T062 | pytest completo (SQLite) | **2942 passed / 23 skipped**; unico fallo el flaky `test_suggest_perf` de SPEC-001, **2 passed** aislado |
| T063 | ruff + mypy | limpios en **416 fuentes** |
| T064 | PostgreSQL 18.6 real | migraciones 000-022 aplicadas e idempotentes; **19 passed** en `test_pg_schema.py` |
| T065 | tsc + ESLint + next build | verdes, **110 paginas**, Middleware 34,1 kB |
| T067 | documentacion | `AGENTS.md` seccion 49 y seccion 46 actualizada; este "Estado real" |
| T068 | checklist de navegacion | **40/40**, y los no automatizables enumerados en `MANUAL` |

El check de constitution de `plan.md` se paso al disenar la feature y no se ha
repetido al cerrar: el principio I (partida doble) y el II (inmutabilidad de
asientos) los cumple el codigo de SPEC-002, que esta feature no toca, y
`test_constitucion_navegacion.py` comprueba lo que si es de esta feature
(aislamiento, `Decimal`, auditoria de escritura, ACID, control de acceso).
