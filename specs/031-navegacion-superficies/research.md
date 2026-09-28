# Research: Navegación y superficies (SPEC-031)

**Fecha**: 2026-09-27 | **Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

Documento de Phase 0. Resuelve los unknowns del Technical Context. Cada decisión
registra qué se eligió, por qué, y qué alternativas se descartaron.

---

## D1. Componentes de navegación de Material Design 3

**Decisión**: rail de navegación colapsado en escritorio con 6 destinos, barra de
navegación inferior de 4 destinos + «Más» en móvil, y rail expandido como panel
contextual de la superficie.

**Racional**: los límites están documentados, no son preferencias. La especificación de
Material Design 3 fija **3-7 destinos** para el navigation rail y **3-5** para la navigation
bar, y dice explícitamente que la navigation bar es para móvil y tableta. Seis destinos
caben en el rail. Seis NO caben en una barra inferior, y la propia especificación dice que
con más de cinco elementos «don't use a navigation bar; the elements may collide», y que
conviene usar en su lugar un **modal expanded navigation rail**.

**Corrección a una afirmación anterior**: dije que el drawer era la pieza adecuada para el
panel de la superficie. Está **desaconsejado**: la actualización M3 Expressive indica que
«the navigation drawer is no longer recommended» y que su sustituto es el **expanded
navigation rail**, que hace lo mismo y adapta mejor entre breakpoints. El panel contextual
se implementa como rail expandido, no como drawer. También queda dicho: «Don't use a
navigation rail on compact screens, use a navigation bar or a modal navigation rail» — de
ahí que en móvil sea barra inferior y no rail.

**Consecuencias**:

- Puntos de ruptura adoptedos de M3: compacto < 600dp, medio 600-839dp, expandido
  840-1199dp, grande 1200-1599dp, extra-grande >= 1600dp. En compacto, barra inferior; a
  partir de medio, rail.
- «Don't use the active indicator for more than one navigation item at a time»: el estado
  activo es un indicador único y exclusivo.
- «Always put the rail in the same place»: el rail no se reposiciona entre pantallas.
- «Keep the label of destinations short and concise. Don't truncate or shrink text»: las
  etiquetas se acortan, no se recortan. Confirma el enfoque de FR-015.
- El perfil de usuario va en la **barra superior**, no en el rail, lo que coincide con la
  zona de contexto de FR-002.

**Alternativas descartadas**: barra inferior de 6 en escritorio (rechazada por la propia
especificación, 3-5); drawer como panel (desaconsejado en M3 Expressive); rail colapsado
con 6 destinos en móvil (rechazado por espacio); Menú desplegable único con las ~50
opciones (rechazado porque M3 exige destinos previsibles, no un volcado de opciones).

---

## D2. Guard de sesión: por qué no basta un middleware

**Decisión**: doble almacén del token (cookie HTTP-only para el borde, `localStorage` para
el encabezado `Authorization` existente) + `middleware.ts` con redirección **optimista** +
guard de cliente para el caso de token caducado. La frontera de seguridad real **no cambia**
y sigue siendo el 401 del backend.

**Racional**: el middleware de Next.js corre en el runtime Edge y **no puede leer
`localStorage`**, solo cookies. El proyecto guarda hoy el token en `localStorage` y todas las
páginas son componentes de cliente, así que no hay ninguna protección de ruta: sin token,
`/asientos/diario` se renderiza igual y solo falla la petición de datos. La documentación de
la comunidad sobre el patrón es explícita sobre el límite: comprobar la presencia de la
cookie es una redirección **optimista** y «THIS IS NOT SECURE»; la verificación real debe
hacerse en cada ruta.

Eso encaja con la decisión del usuario de dejar la app funcional y tratar la seguridad
en SPEC-032: el guard de esta feature es **experiencia de usuario** (FR-001 dice «impedir el
acceso», no «proteger»), y el control de seguridad sigue donde ya está y ya funciona.

**Consecuencias**:

- Al iniciar sesión, el token se escribe en cookie HTTP-only y en `localStorage`.
- `middleware.ts` con `matcher` sobre las rutas de negocio: si no hay cookie, redirige a
  `/login` sin revelar el shell. Es una mejora perceptible, no un control.
- Un `<SessionGuard>` de cliente en el layout detecta el caso real (cookie presente pero
  token caducado) a partir del 401 del backend, limpia la sesión y redirige. Cubre el
  escenario de recuperación de CHK022.
- La expiration del token es de 30 minutos (SPEC-044 §44), lo que hace este caso frecuente
  en uso diario y justifica el guard de cliente.
- Ningún componente de navegación debe asumir que el token es válido: la única fuente de
  verdad es la respuesta del backend.

**Alternativas descartadas**: solo `middleware.ts` (deja pasar el token caducado y, sobre
todo, no protege nada: el backend ya protege); solo guard de cliente (muestra el shell un
instante antes de redirigir, que es exactamente lo que FR-001 quiere evitar); mover el
proyecto a Server Components (rechazado por coste: las 103 pantallas son de cliente y
convertirlas excede esta feature).

---

## D3. Contexto de ejercicio activo

**Decisión**: `X-Ejercicio-Activa` como cabecera, con estado en cliente indexado por
`(empresa, ejercicio)`, validación en servidor contra la empresa de la sesión, y el parámetro
explícito de la URL ganando sobre la cabecera.

**Racional**: no existe ningún concepto de ejercicio activo (`ejercicio_activo` no aparece
en el código). La constitution III exige que `empresa_id` se derive exclusivamente del
contexto autenticado y **nunca de datos del cliente**; `X-Empresa-Activa` ya es un valor
recibido del cliente y funciona porque el servidor lo valida contra la sesión. El ejercicio
se trata igual: es una entrada no confiable que se valida. La diferencia es que el ejercicio
**no es una frontera de tenant** sino un filtro dentro del tenant, y por eso se valida contra
la empresa en lugar de contra la sesión directamente.

**Consecuencias**:

- `get_ejercicio_activa()` en `api/deps.py`, con la misma política que `get_empresa_id`.
- Si no llega cabecera, se usa el año en curso; si ese ejercicio no existe para la empresa, se
  devuelve el más reciente en vez de fallar (caso borde de empresa sin ejercicio).
- Precedencia: `?ejercicio=2025` explícito **gana** a la cabecera. La cabecera es valor por
  defecto, nunca coerción. Esto evita que un `POST` con `?ejercicio=2025` se impute al
  ejercicio de la cabecera.
- El estado se guarda por `(empresa, ejercicio)`, no como valor global, porque el mismo
  usuario puede estar en 2025 en la empresa A y en 2026 en la empresa B.
- Cambio de empresa o de ejercicio **MUST invalidar** las consultas en caché del cliente, con
  la misma regla que ya usa el cambio de empresa.

---

## D4. Reconciliación de las dos fuentes de estado de ejercicio

**Decisión**: `EjercicioContable` (SPEC-009) es la fuente de verdad del ciclo de vida, y el
estado expuesto al cliente es el **más restrictivo** de las dos fuentes.

**Racional**: existen dos conceptos que pueden discrepar. `FiscalYear` (SPEC-004) tiene
`is_closed` booleano y lo usan `GET /fiscal-years` y `cerrar_ejercicio`. `EjercicioContable`
(SPEC-009) tiene `estado` con tres valores (`abierto`, `cerrado`, `con_apertura`) y lo usan la
apertura y el cierre. Un mismo año puede estar `abierto` en una y cerrado en la otra. El
selector expondría esa incoherencia: mostraría «abierto» y la escritura sería rechazada, que es
la peor combinación posible en un control de entrada.

**Consecuencias**:

- Se elige `EjercicioContable` porque modela el ciclo de vida (tres estados) y es la que usan
  los servicios de apertura y cierre.
- El estado derivado: `cerrado` si cualquiera de las dos fuentes dice cerrado; si no,
  `con_apertura` si `EjercicioContable` lo dice; si no, `abierto`. Con `FiscalYear` inexistente
  se trata como abierto, que es la convención ya establecida en SPEC-004.
- FR-019 se cumple por construcción: la información mostrada y la posibilidad de escribir no
  pueden discrepar, porque el mismo estado derivado gobierna ambas.
- CHK014 queda resuelta por esta decisión: cuando las fuentes discrepan, se muestra el estado
  más restrictivo.

**Alternativas descartadas**: unificar las dos tablas (fuera de alcance, tocaría 15 specs);
usar `FiscalYear` como fuente (no tiene el estado `con_apertura`, que el selector necesita
para distinguir el caso de cierre reabierto).

---

## D5. Almacenamiento de los favoritos

**Decisión**: tabla nueva `favorito_usuario`, migración `022_favoritos.sql`, con unicidad
`(empresa_id, usuario_id, destino)`.

**Racional**: hoy solo hay dos claves en `localStorage` (token y empresa). Un favorito en
`localStorage` es **por navegador**, no por usuario: el conjunto que alguien fija en el PC de
la oficina no existe en el portátil, y dos personas que comparten equipo lo comparten. Como el
dato es por usuario y por empresa, la constitution III exige `empresa_id` en la clave.

`destino` es una **clave estable del mapa de superficies**, no una ruta. Si mañana se renombra
una ruta, el favorito sigue resolviendo (FR-026), que es el requisito de la historia 6.

**Consecuencias**:

- Número `022` libre: las migraciones existentes llegan a `021_adjuntos_asiento.sql`.
- Registro en `db/migrate.py` (`ORDEN_PREFERENTE`) y en `test_migrations.ESPERADAS`, que es
  donde falla `test_orden_por_dependencias` si se olvida.
- `orden` entero para respetar el orden elegido por el usuario. El límite de FR-025
  opera **en la lectura, no en la escritura**: un favorito por encima del máximo
  **se guarda**, se muestra recortado a 5 y se avisa, y nunca se borra. Si se
  rechazara en la escritura con 422, el usuario con 5 favoritos no podría añadir el
  suyo y perdería la opción, que es justo lo que el requisito prohíbe. El 422 queda
  solo para un `orden` con valor fuera de rango, que es otra cosa.
- Marcar y desmarcar favoritos son **operaciones de escritura** y por tanto MUST auditarse
  (constitution, sección de stack). Ver D9.
- Sin trigger de inmutabilidad: los favoritos son la única entidad de esta feature que se
  borra, y el borrado es la baja lógica de un marcado, no una pérdida de evidencia contable.

**Alternativas descartadas**: `localStorage` (por navegador, no portable); una columna JSON de
favoritos en `users` (no permite la unicidad por empresa ni ordenar sinerializar y reescribir
todo el documento en cada marcado); carpeta de marcadores del navegador (fuera del sistema y
sin control de permisos).

---

## D6. Mapa de superficie a permiso

**Decisión**: cada destino declara su permiso requerido de forma estática en el mapa de
superficies, y el cliente lo cruza con `GET /permisos/mis-permisos` ya existente.

**Racional**: el rail y el panel deben ocultar lo que el usuario no puede abrir (caso borde de
la pérdida de rol), y los favoritos deben ocultarse sin borrarse (FR-024). Ya existe
`GET /permisos/mis-permisos`, que devuelve `{rol_id, rol, permisos}` para el rol del usuario en
la empresa activa, y los tres roles base (`ADMIN`, `ACCOUNTANT`, `READ_ONLY`) tienen al menos
`acct:ver`.

**Alternativas descartadas**: derivar el permiso de cada destino consultando
`routes_registry.inventario_permisos` en el cliente (ese registro mapea rutas **API** a
permisos, y un destino de navegación no es una ruta API: la correspondencia sería frágil);
ocultar por 403 y reintentar (produce destinos rotos visibles, que es justo lo que el caso
borde prohíbe).

---

## D7. Operabilidad por teclado

**Decisión**: toda la navegación nueva es operable por teclado y **no captura** atajos que la
pantalla de entrada contable ya use.

**Racional**: es el único punto donde esta feature roza una norma de la constitution. La
sección «Normas del Frontend» exige «priorizando la usabilidad por teclado (teclas de acceso
rápido, tabulación fluida y atajos) para la introducción masiva de asientos», y el ámbito
literal de esa norma es la pantalla de entrada, que esta feature no reconstruye. Pero un rail
nuevo se interpone en el camino hacia esa pantalla: si captura `Tab`, `Enter` o las flechas,
degrada un flujo que la constitution declara obligatorio. Por eso no es una mejora opcional
sino una restricción del gate.

Además el spec tiene **0 de 29** requisitos de teclado, lo que `checklists/navegacion.md`
detectó en CHK029 y CHK031. Esta decisión los cubre.

**Consecuencias**:

- Orden de tabulación: zona de contexto → rail → panel → contenido.
- Indicador de foco visible en todos los elementos navegables, incluidos los estados
  ámbar y rojo del ejercicio.
- El estado del ejercicio **no se transmite solo por color**: lleva etiqueta de texto
  (`cerrando`, `cerrado`), lo que además satisface CHK030.
- Prohibido registrar atajos globales de una sola tecla en la navegación; los atajos con
  modificador quedan fuera del alcance de esta feature.
- `Enter` en un destino navega; las flechas se reservan al panel cuando tiene foco.

**Alternativas descartadas**: replicar los atajos de la pantalla de asientos (acopla dos
componentes distantes); diferir accesibilidad a SPEC-032 (la constitution ya la exige hoy).

---

## D8. Consolidación de rutas

**Decisión**: las 5 consolidaciones se resuelven con `redirects()` de `next.config.mjs` más
una página canónica nueva, no con scripts de redirección en el cliente.

**Racional**: un redirect de Next es de servidor, no monta un componente, no aparece en el
historial como navegación real y no requiere que cada página cambie. Además el caso de
`/contabilidad/asientos/nuevo` duplica exactamente a `/asientos/nuevo`, y `/contabilidad/import-export`
es el import/export de asientos: son la misma función en dos sitios.

**Mapa de consolidaciones**:

| Dirección antigua | Canónica | Motivo |
|---|---|---|
| `/contabilidad/asientos/nuevo` | `/asientos/nuevo` | duplicado exacto |
| `/contabilidad/import-export` | `/asientos/import-export` | es el import/export de asientos |
| `/cierre` | `/cierres` | duplicado |
| `/cobros` | `/vencimientos` | ambiguo: los medios de pago viven en `/tesoreria/cobros` |
| `/tesoreria/efe` | `/efe` | reubicado a la superficie Informes |

**Consecuencias**: `/contabilidad` deja de ser un prefijo de Screens y pasa a ser la landing de
la superficie Contabilidad, así que el redirect de la ruta hija no colisiona con ella. Los
favoritos guardan claves de destino, no rutas, así que no se ven afectados (FR-026).

---

## D9. Reconciliación de dos contradicciones del spec

**Decisión**: las dos contradicciones que encontró `checklists/navegacion.md` se resuelven en
favor del criterio más específico.

- **CHK013 (límite de favoritos)**: FR-025 dice «limitar el número» sin cifra; SC-007 dice 5.
  Se adopta **5** y FR-025 MUST reformularse con la cifra. Motivo: un requisito sin cifra no es
  comprobable, y el criterio de éxito ya fija el número.
- **CHK016 (independencia de las historias P1)**: las tres historias P1 se declaran
  independientes, pero FR-001 bloquea toda opción sin sesión. Se anota como **redacción
  engañosa, no contradicción funcional**: cada historia sigue siendo demostrable por separado
  porque la historia 1 ES la sesión. No requiere cambio de requisitos, sino de la afirmación de
  independencia en el spec.

**Auditoría de favoritos**: la constitution obliga a registrar cada operación de escritura con
usuario, timestamp UTC, IP, operación y payload, en la misma transacción ACID. Marcar y
desmarcar son escrituras, así que MUST llamar a `registrar_auditoria` dentro del boundary de
`get_db`. No es aplazable a SPEC-032.

---

## D10. RBAC: ningún módulo nuevo

**Decisión**: no se crea módulo RBAC nuevo. La feature **no introduce endpoints de escritura
de negocio**, solo el contexto (lectura) y los favoritos (preferencia de usuario, no dato
contable).

**Racional**: el catálogo tiene 15 módulos. Añadir uno obliga a actualizar los tres sitios
coherentes (`catalogo.py`, `007_rbac.sql`, trigger `trg_companies_rbac_seed`) y los recuentos
de los tests de SPEC-015, que es un coste alto para una ganancia de navegación.

**Consecuencias**:

- `GET /api/v1/contexto` con guard `require_permission("acct", "ver")`, que los tres roles
  base poseen. Es además la respuesta a FR-006, redactado como propiedad y no como nombre de
  permiso.
- Los endpoints de favoritos usan `acct:ver` para leer y `acct:editar` para marcar, por ser
  una acción del usuario sobre su propia configuración.
- `api.routes_registry.rutas_sin_permiso` MUST seguir en 0.
- El plan mantiene `catalogo.py` como MODIFICADO, pero el cambio real es **ninguno**: se
  documenta en el tree para dejar constancia de que se evaluó y se descartó.

---

## Resumen de unknowns resueltos

| # | Unknown del Technical Context | Decisión | Estado |
|---|---|---|---|
| 1 | Límites de destinos de M3 | rail 3-7, barra 3-5, rail expandido | D1 |
| 2 | Mecanismo del guard de sesión | cookie + localStorage, middleware optimista | D2 |
| 3 | Contexto de ejercicio activo | cabecera validada, estado por empresa | D3 |
| 4 | Fuente de verdad del estado de ejercicio | `EjercicioContable` + estado más restrictivo | D4 |
| 5 | Almacenamiento de favoritos | tabla `favorito_usuario`, migración 022 | D5 |
| 6 | Mapa superficie a permiso | declaración estática + `mis-permisos` | D6 |
| 7 | Operatividad por teclado | obligatorio, sin captura de atajos | D7 |
| 8 | Consolidación de rutas | `redirects()` de Next | D8 |
| 9 | Contradicciones del spec | límite 5; independencia es matiz de redacción | D9 |
| 10 | Módulo RBAC | ninguno nuevo, reutilizar `acct` | D10 |

Sin NEEDS CLARIFICATION pendientes.
