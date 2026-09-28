# Research: Multiempresa y Control de Acceso por Roles (SPEC-003)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Resoluciones de los unknowns del Technical Context y decisiones de diseño conforme a la constitución y al plan raíz.

## D1. Modelo de relación usuario-empresa-rol

- **Decision**: Entidad de unión `user_companies` con `UNIQUE (user_id, company_id)` y un único rol por par entre `ADMIN`, `ACCOUNTANT`, `READ_ONLY` (FR-006). El usuario es global; la empresa y el rol son específicos del par.
- **Rationale**: Un usuario puede pertenecer a varias empresas con distinto rol (constitución III); el rol por par permite la matriz de permisos sin duplicar usuarios.
- **Alternatives considered**: Rol almacenado en el usuario (un solo rol global → rompe multiempresa); tabla de roles separada con permisos puntuales (sobre-ingeniería para el mínimo exigido).

## D2. Empresa por defecto del usuario

- **Decision**: Columna `is_default` en `user_companies`, con **índice único parcial** `UNIQUE (user_id) WHERE is_default` (una sola empresa por defecto por usuario). Se devuelve en el login y se usa al iniciar el contexto de empresa.
- **Rationale**: FR-001 exige "empresa por defecto" en el login; el índice parcial garantiza unicidad en base de datos.
- **Alternatives considered**: Empresa por defecto calculada (primera de la lista, inestable); columna en `users` (mezcla datos globales con específicos de empresa).

## D3. Sesión y transporte de la empresa activa (JWT)

- **Decision**: Token **JWT** de sesión con claims estándar (sub=user_id, exp/nbf/iat/jti, aleatorio) y **empresa activa NO en el token**: la empresa activa viaja en la cabecera `X-Empresa-Activa` de cada petición y es validada en cada guard contra las `user_companies` activas del usuario. La conmutación de empresa actualiza solo el contexto (cabecera/sesión de frontend), sin re-auth.
- **Rationale**: La empresa activa es contexto transitorio del usuario, no una credencial durable; validarla por petición contra la relación activa permite detectar revocaciones/desactivaciones y cumple FR-002/FR-009 (conmutación sin arrastre de datos).
- **Alternatives considered**: `empresa_id` en el claim del JWT (quedaría congelada hasta expirar; la conmutación exigiría emitir tokens nuevos y la revocación no sería inmediata); empresa en el body (prohibido: dato no confiable).

## D4. Guard de contexto y RBAC (`deps`)

- **Decision**: Dependencias compartidas `get_current_user` (valida JWT), `get_empresa_id` (lee `X-Empresa-Activa`, comprueba relación activa usuario-empresa; **403 sin distinguir "empresa no existe" de "sin permiso"**) y `require_role(*roles)` (matriz mínima: `READ_ONLY` bloqueado en cualquier endpoint de escritura). Sin contexto de empresa → 403 (no existe operación "sin empresa").
- **Rationale**: FR-002/FR-003/edge-cases exigen denegar sin revelar información; centralizar el guard en deps evita que cada feature repita el patrón y garantiza coherencia (FR-010).
- **Alternatives considered**: Middleware global que filtra por path (fragil: excepciones por endpoint); validación solo en los servicios (le deja a cada feature la tarea).

## D5. Creación de empresa con seed del PGC en la misma transacción

- **Decision**: `POST /api/v1/companies` inserta `companies` + `user_companies(ADMIN, is_default=true)` y ejecuta `seed_default_pgc(p_company_id)` (SPEC-001) todo dentro del mismo `async with async_session.begin()` — o delega en el trigger `trg_companies_seed` del plan raíz. Si el seed falla, la empresa no existe (atomicidad).
- **Rationale**: FR-007 exige ADMIN + plantilla base; la constitución exige atomicidad; el seed por tenant garantiza el aislamiento desde el primer registro (SC-005).
- **Alternatives considered**: Seed asíncrono tras el alta (empresa sin cuentas temporalmente → inconsistente); seed manual por el admin (fiable pero rompe SC-005).

## D6. Conmutación de empresa sin re-login

- **Decision**: Endpoint `POST /api/v1/auth/switch-company` con body `{ "company_id" }` que revalida la relación activa y devuelve un **nuevo contexto** (token/ cabecera resultante) sin emitir nuevas credenciales; la sesión de frontend actualiza su estado global de empresa (recargando el contexto). El cambio a una empresa sin relación → 403 y la empresa activa permanece (edge case).
- **Rationale**: FR-004/FR-009/SC-004 (< 1 s, sin re-login, sin exposición de otras empresas).
- **Alternatives considered**: Emitir un token nuevo por conmutación (recarga inútil de credenciales y altura de token); conmutación local en frontend sin revalidación (permite operar sobre empresa sin acceso).

## D7. Listado solo de empresas accesibles y activas

- **Decision**: Toda consulta de "mis empresas" filtra `user_companies` por `user_id` **+ `is_active` de empresa** + `is_active` del usuario; una relación se considera activa solo si ambos lo están (FR-008). Logout descarta el contexto local; no hay operación válida sin empresa.
- **Rationale**: Edge cases (empresa inactiva, usuario inactivo) deben denegar; la "relación activa" es la fuente de verdad del aislamiento.
- **Alternatives considered**: Filtrar solo por relación (permite operar sobre empresas inactivas); cachear roles (revocaciones diferidas).

## D8. Matriz de permisos por rol (mínimo)

- **Decision**: Definir en esta feature la matriz mínima: `READ_ONLY` no puede ejecutar **ningún** endpoint de escritura (cuentas, asientos, cierre, facturas, conmutaciones de rol); `ACCOUNTANT` opera contable (cuentas/asientos/informes) salvo cierre?; `ADMIN` todo (incluye cierre y gestión). El mapeo exacto endpoint→rol se fija en `backend/src/api/deps.py` (roles exigidos por feature, ver contracts).
- **Rationale**: FR-006 exige mínimamente bloquear la escritura de `READ_ONLY`; una matriz central evita divergencias entre features.
- **Alternatives considered**: Matriz incompleta deferida a cada feature (riesgo de agujeros de autorización); roles con permisos desnormalizados por tabla (excesivo para el alcance).

## D9. Auditoría del circuito de acceso

- **Decision**: `login`, `switch-company` y `create-company` escriben `audit_log` (empresa_id cuando aplica, actor, acción `LOGIN`/`SWITCH_COMPANY`/`CREATE_COMPANY`, IP, payload) **dentro de la misma transacción** (para create-company) o transacción del evento (switch seguro de lectura+escritura). El `login` fallido no audita datos sensibles.
- **Rationale**: Constitución (auditoría inmutable, misma transacción ACID); trazabilidad del cambio de contexto (SC-004).
- **Alternatives considered**: Auditar solo operaciones de datos (pierde el contexto de sesión); log externo (fuera de la atomicidad).

## D10. Hashing de credenciales y expiración

- **Decision**: Contraseñas con **bcrypt/argon2** (coste configurable, salt automático); JWT con expiración (p. ej. 8-24 h) y `jti` para invalidación opcional; nunca almacenar plaintext.
- **Rationale**: Práctica de seguridad estándar; la expiración fuerza renovación y limita el window de un token robado.
- **Alternatives considered**: JWT sin expiración (riesgo elevado); almacenar hash débil (SHA) → prohibido.
- **NEEDS CLARIFICATION**: algoritmo hash final (bcrypt vs argon2) y duración exacta del token — se resuelven en tareas T009/T013 con la configuración del proyecto.

## D11. Stack e integración

- **Decision**: Backend **FastAPI async + SQLAlchemy 2.x async + asyncpg** en `services/auth`; frontend Next.js gestiona el estado global de empresa y envía `X-Empresa-Activa` en **todas** las peticiones de datos; el cambio de empresa recalcula el contexto sin arrastrar estado previo (SC-003).
- **Rationale**: Coherencia con la constitución y el plan raíz; el aislamiento se decide en el backend.
- **Alternatives considered**: Estado de empresa en localStorage sin validación en backend (rompe aislamiento); único token sin cabecera de empresa (sin contexto multiempresa).