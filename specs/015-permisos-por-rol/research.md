# Research: Matriz de Permisos por Rol (SPEC-015)

**Fecha**: 2026-09-16 | **Feature**: [spec.md](spec.md)

Resoluciones de los unknowns del Technical Context y decisiones de diseño conforme a la constitución y al plan raíz. Se apoya en SPEC-003 (identidad, sesión y determinación de la empresa activa); esta feature añade la capa de autorización por operación.

## D1. Catálogo de módulos y operaciones (lista cerrada)

- **Decision**: Definir un **catálogo estático de operaciones** (semilla) por módulo de negocio — el conjunto de operaciones que la API expone (`ver`, `crear`, `editar`, `aprobar`, `importar_exportar`, `configurar`, `baja`/`cerrar` donde aplique) — en `PermisoOperacion`. La matriz referencia operaciones del catálogo; una operación inexistente no puede concederse (se deniega y se audita).
- **Rationale**: FR-001/FR-002 exigen permiso por operación; un catálogo cerrado impide "permisos inventados" y simplifica la evaluación por clave (módulo, operación, rol, empresa).
- **Alternatives considered**: Operaciones libres tipo string (permite errores y concede por defecto si se escribe mal; viola la SP); lista derivada de los routers automáticamente (acopla visibilidad interna con autorización, descartado).
- **NEEDS CLARIFICATION**: confirmar el catálogo concreto de módulos a cubrir en esta fase (¿los módulos de SPEC-001/002/011/013/014/016/020 completos o un subconjunto inicial?) y su enumeración en `PermisoOperacion`.

## D2. Denegación por defecto y mínimo empresa × rol × operación

- **Decision**: La matriz solo **concede** (no existe "deniega" explícito): la ausencia de fila `(empresa, rol, permiso)` implica **denegado**. La decisión final = `empresa activa ∩ rol del usuario ∩ permiso solicitado`. Un usuario con rol `ADMIN` hereda las denegaciones por defecto (no es privilegio global: en su empresa solo lo que la matriz concede) y en otra empresa no tiene acceso aunque su rol global lo parezca (constitución III).
- **Rationale**: FR-002 (denegar por defecto), FR-003 (mínimo empresa×rol×permiso), Edge Cases (administrador hereda denegaciones; multiempresa estricta).
- **Alternatives considered**: Tabla con fila explícita `denegado` (peculios de borrado; la ausencia ya es denegación y es más simple y segura); rol `SUPER_ADMIN` global (contradice la Assumption "no existe superusuario global", descartado).

## D3. Evaluación por petición (sin cacheo que deteriore revocaciones)

- **Decision**: La autorización se evalúa **en cada petición** consultando la matriz de la empresa activa (índice por empresa+rol+módulo+operación, cache solo de la tabla de catálogo operaciones que es estática). Revocar un permiso surte efecto inmediato en la siguiente petición.
- **Rationale**: La Assumption de la spec es explícita (no cachear en exceso para evitar permisos caducados); el coste de la consulta simple es <10 ms.
- **Alternatives considered**: Cache en memoria del usuario con TTL (riesgo de permisos vivos tras revocación; se descarta salvo evolución con invalidación por evento).

## D4. Dependency central `require_permission` y no-bypass

- **Decision**: Una dependency de FastAPI **`require_permission(modulo, operacion)`** en `backend/src/api/deps.py` se aplica **en cada router** expuesto (SPEC-001/002/011/013/014/016/020...). La verificación: (1) identidad de SPEC-003 → (2) empresa activa de sesión → (3) rol del usuario en la empresa → (4) fila en la matriz → (5) `allow`. Cualquier fallo → `403` con evento auditado. Los tests (contract) verifican que ningún endpoint de módulos con datos prescinde de la dependency (SC-004).
- **Rationale**: FR-003 exige verificación en cada operación sin bypass; una dependency única evita olvidos y duplicaciones.
- **Alternatives considered**: Decoradores sobre funciones (no se integran con OpenAPI ni con DI de FastAPI; se descarta); middleware global (no distingue operación/módulo con precisión y complica los tests; se descarta).

## D5. Aislamiento multi-empresa en la matriz

- **Decision**: `MatrizPermiso` lleva `empresa_id` en PK/índices; la evaluación usa **solo** la matriz de la empresa activa. El rol del usuario en SPEC-003 es por empresa. Pruebas de integración demuestran que un rol con permiso en la empresa A no concede nada en la B y que la administración de la matriz de A no es accesible desde B (404).
- **Rationale**: FR-004 y SC-005; constitución III.
- **Alternatives considered**: Matriz global con excepciones por empresa (rompe el aislamiento estricto y la denegación por defecto; descartado).

## D6. Administración de la matriz (configuración por empresa)

- **Decision**: Los endpoints de gestión de la matriz se restringen a la operación de configuración que la propia matriz concede (auto-seed de la empresa con `ADMIN` → `configurar`). La siembra inicial de roles base (`ADMIN`, `ACCOUNTANT`, `READ_ONLY` de la Assumption) y de la matriz inicial ocurre en la creación de la empresa (SPEC-003).
- **Rationale**: FR-006 (configuración restringida a la matriz de configuración); la Assumption pide roles sembrados desde la creación de la empresa.
- **Alternatives considered**: Permitir que cualquier `ADMIN` configure sin fila de matriz (introduce un bypass a la denegación por defecto; descartado).

## D7. Auditoría de intentos denegados y permisos concedidos

- **Decision**: Cada **intento denegado** de una operación con datos contables y cada **permiso concedido** sobre datos contables generan un `EventoAuditoriaAcceso` (empresa, usuario, actor, módulo, operación, resultado allow/deny, timestamp UTC, IP, payload) persistido **en la misma transacción ACID** que la operación (o su denegación). El evento es inmutable (sin UPDATE/DELETE).
- **Rationale**: FR-005 y SC-003; constitución (auditoría inmutable ACID). Auditar también los `allow` sobre datos contables mantiene SC-003 sin asfixiar el log en accesos de solo lectura masivos.
- **Alternatives considered**: Auditar solo `deny` (falla SC-003 en el caso "permiso concedido"); auditar absolutamente todo `allow` incluyendo lecturas triviales (log ruidoso; se limita a operaciones sobre datos contables según FR-005).
- **NEEDS CLARIFICATION**: definir con qué detalle de payload (solo tabla/IDs o cuerpo completo anonimizado) se auditan los `allow` sobre asientos.

## D8. Modificación de permisos (editar, revocar) y fila de catálogo

- **Decision**: La matriz se gestiona por alta/baja de filas `(empresa, rol, permiso)`; no existe edición in-place (una revocación es una fila que desaparece). El rol y el permiso operado se auditan en la misma transacción.
- **Rationale**: Simple, auditable y coherente con la denegación por defecto (sin estados intermedios).
- **Alternatives considered**: Campo `concedido` para desactivar filas (complejidad sin beneficio; la ausencia ya deniega).

## D9. Stack e integración

- **Decision**: Backend **FastAPI async + SQLAlchemy async + asyncpg**; la dependency `require_permission` usa sesión `async` con `async with async_session.begin()` solo en operaciones de escritura (auditoría); la evaluación de lectura usa sesión de solo lectura; frontend Next.js oculta los módulos/operaciones no permitidos devolviendo la matriz de la empresa (UI informativa; la seguridad vive en el backend).
- **Rationale**: Coherencia con la constitución y el `plan.md` raíz; la UI nunca es el control de seguridad.
- **Alternatives considered**: Ocultar en frontend como única medida (bypass trivial; descartado).

## D10. Pruebas obligatorias y contrato de no-bypass

- **Decision**: Suite pytest con: (1) tests unit de evaluación (ausencia = denegado, mínimo empresa×rol×permiso, rol inexistente → denegado); (2) tests de integración de aislamiento (rol con permiso en A no actúa en B); (3) tests de contrato que **enumeran los routers registrados** y verifican que cada uno usa `require_permission` para sus operaciones con datos (SC-004 sin bypass). El inventario de routers se expone para el test como metadatos de la app.
- **Rationale**: Constitución V y SC-004; un "no-bypass" no es verificable sin un test que lo atraviese.
- **Alternatives considered**: Revisión manual en code review (insuficiente como garantía autmatizada; se conserva como refuerzo en Polish).