# Correcciones provisionales — 2026-09-29

Trabajo **fuera del ciclo de specs**, a petición del usuario sobre la aplicación en
funcionamiento. Son correcciones de la aplicación, no features nuevas, y por eso
van aquí y no en un `specs/0XX-*/`. Cuando se den por buenas, se abren las specs
afectadas y se corrigen sus artefactos (§5).

Tres bloques: las dos cosas que se pidieron, y una tercera que no estaba en el
encargo y que hacía inútil la primera.

| # | Qué se corrigió | Specs afectadas |
|---|---|---|
| [1](#1-importar-el-xlsx-del-banco) | Importar extracto bancario en XLSX (el formato que da el banco) | **SPEC-013** (principal), SPEC-031 (superficie de conciliación) |
| [2](#2-cambiar-de-empresa-de-ejercicio-y-cerrar-sesion) | Menú de sesión: cambiar empresa, cambiar ejercicio, cerrar sesión | **SPEC-031** (zona de contexto), SPEC-003 (sesión/logout) |
| [3](#3-las-tablas-de-conciliación-no-existían-en-postgresql) | **Las 6 tablas de SPEC-013 no tenían migración**: la conciliación entera era inservible en la aplicación real | **SPEC-013** |

> **El 3 no estaba en el encargo y ha tenido que entrar.** Sin él, el 1 compila,
> pasa todos los tests y devuelve un **500** en la aplicación real. Se detectó al
> probar contra PostgreSQL, no al leer el código. Está aquí porque entregar el 1 sin
> el 3 habría sido entregar algo que no funciona.

---

## 1. Importar el XLSX del banco

### Qué pasaba

El fichero `Data/1. MovimientosCuenta ene_feb26.xlsx` no se podía importar. No por un
error concreto, sino porque **el formato no estaba soportado en ninguna capa**:

| Capa | Estado antes | Fichero |
|---|---|---|
| Selector de ficheros del navegador | `accept=".txt,.csv"` — el `.xlsx` ni siquiera aparecía en el diálogo | `frontend/src/app/conciliacion/importar/page.tsx:59` |
| Desplegable de formato | Solo dos opciones: `norma_43_1919` y `csv_normalizado` | ibídem, líneas 70–71 |
| API | `layout` era un `str` **sin validar**: cualquier valor desconocido caía en silencio en el parser de la norma 43 | `backend/src/api/reconciliation.py:117` |
| Parser | Dos formatos. El despacho era un `if`: `csv` → CSV, **todo lo demás** → norma 43 | `backend/src/services/reconciliation/parsers.py:212-215` |

El resultado era un error que no decía nada del problema real: subir el XLSX con el
desplegable en
«Norma 43/19» contestaba

```
422 · línea 1: longitud 22 != 100
```

hablando del **ancho de línea de un fichero que no es de ancho fijo**. Y subirlo
con `layout=xlsx` tampoco: `xlsx` no era un valor válido y caía en la norma 43 por el
mismo camino. Los tres caminos dan un error que no señala el problema.

### Por qué estaba así

No es un olvido de la última sesión. `research.md` de SPEC-013 (líneas 10–12) lo
desestimó explícitamente:

> **Alternatives considered**: Solo CSV (pierde el estándar bancario); parseo rígido
> de la norma 43 (rompe con variantes de entidad). **UE: formato XLSX/qif
> desestimados por no estar en la spec.**
> **NEEDS CLARIFICATION**: … y si `XLSX` es imprescindible o basta norma 43/CSV.

Es decir, estaba **documentado como pregunta abierta** y se cerró dando por bueno el supuesto equivocado.
La spec asumía que la banca daría norma 43 o CSV. La pregunta quedó sin responder y
el caso real resultó ser el tercero.

### Qué se ha hecho

#### El formato, tal y como viene

El XLSX del banco no es un fichero de ancho fijo, es una hoja de calculo con
caracteristicas concretas:

| Característica | Valor real | Consecuencia en el parser |
|---|---|---|
| Bloque de metadatos | 7 filas encima (titular, saldos, IBAN, rango de fechas) | La cabecera **se busca** en las 40 primeras filas, no se asume en la 1 |
| Fechas | Texto `DD/MM/AAAA` (no son fechas de Excel, aunque el formato de celda diga `mm-dd-yy`) | Se aceptan las 4 formas: texto `DD/MM`, texto ISO, `datetime` y `date` |
| Signo | **Va dentro del importe**: los cargos son negativos | `importe = abs(valor)` y `signo = "D" si valor < 0` |
| Saldos | Una columna `Saldo` con el saldo **posterior** a cada movimiento | No hay `saldo_inicial`: hay que derivarlo |
| Orden | Del más reciente al más antiguo | Se invierte a cronológico, como las otras dos variantes |
| Divisa | Columna `Divisa` (se repite: la del importe y la del saldo) | Se rechaza si no es EUR |

**Lo del saldo inicial es lo no obvio.** El XLSX no lo trae: trae el saldo después de
cada movimiento. Esa columna hace el papel que en la norma 43 hace el registro de
control `98`, y de ahí salen los dos saldos con una sola comprobación:

```
s[i] - importe[i] == s[i + 1]     para todo i     (orden descendente)
```

Si la columna está bien, los saldos encadenan. Si no — un movimiento de más, uno de
menos, un importe mal pegado — se rompe la cadena y **el extracto se rechaza**.
Es la misma garantía que da el registro `98` en la norma 43, conseguida sin
registro de control porque la columna de saldos lo hace sola. Se aceptan las dos
ordenaciones (ascendente y descendente) porque un exportador propio entregaría lo
contrario, y se deduce cuál encaja en lugar de mirar la primera fecha.

El saldo inicial derivado del fichero real es **1863,74** y el final **5281,99**;
`Σ movimientos = 3418,25 = 5281,99 − 1863,74`. Cuadra.

#### Cambios

| Fichero | Cambio |
|---|---|
| `services/reconciliation/layouts.py` | Nuevo catálogo `LAYOUTS` (nombre → etiqueta), `LAYOUTS_XLSX`, y las columnas obligatorias/opcionales del XLSX. Antes no había **ninguna** lista de formatos: solo existían los que el parser atendía de forma especial. |
| `services/reconciliation/parsers.py` | `parse_xlsx_bancario()` y sus ayudantes (`normalizar_columna`, `importe_de_celda`, `_fecha_xlsx`, `_buscar_cabecera`, `_saldo_final_desde_cadena`, `_divisa_eur`, `_referencia_xlsx`, `_iban_de_la_hoja`). `ExtractoDTO` gana `iban`. `parse_extracto` pasa a **rechazar** un `layout` desconocido en vez de caer en la norma 43. |
| `api/reconciliation.py` | `_validar_layout()`: 422 `layout_desconocido` **con la lista de los que sí valen**. Se valida antes de leer el fichero. |
| `services/reconciliation/importacion.py` | El error `cuenta_requerida` dice cuál es el IBAN del extracto. El `payload` de auditoría lleva `layout`, `iban` y `saldo_inicial`. |
| `frontend/.../importar/page.tsx` | Tercera opción en el desplegable; `accept` con `.xlsx,.xlsm`; el formato **sigue al fichero** elegido; texto de ayuda por formato; aviso y botón deshabilitado cuando el XLSX no trae código de cuenta. |

#### La cuenta hay que seguir poniéndola a mano

El XLSX trae el **IBAN**, no el código del plan de cuentas. Un IBAN no es una cuenta
572, y la aplicación no tiene (ni debe tener) una tabla que mapee IBAN → cuenta: eso
es un maestro de bancos que no existe en ninguna spec. Así que el campo «Cuenta 572»
sigue siendo obligatorio para este formato, y ahora la interfaz lo dice **antes** de
subir en vez de devolver un 422 después.

**Pendiente de decidir** (no se ha hecho): persistir el IBAN. Ahora mismo solo
queda en el `payload` de la auditoría, que es la única traza de qué cuenta se
subió. Si se quiere, sería una columna en `extracto_bancario` + migración, y un
selector IBAN → cuenta. No es un arreglo, es una feature: queda anotado en §4.

#### Lo que se ha rechazado a propósito, y por qué

- **Un extracto que no está en euros.** El extracto no lleva tipo de cambio, así que
  importarlo tal cual daría un extracto *falso* con cifras equivocadas y un saldo
  que no cuadra con el banco. Es peor que no importarlo → `422 divisa_no_soportada`.
- **`float` para dinero.** Las celdas del XLSX llegan como `float` porque las ha
  escrito el banco. `Decimal(5281.99)` es `5281.989999999999781...`, no el importe
  del banco; `Decimal(str(5281.99))` sí lo es, porque `str` de un flotante devuelve
  la cadena decimal más corta que vuelve a ese mismo flotante. Se cuantiza a 4
  decimales (la escala de `NUMERIC(18,4)`). Mismo criterio que
  `importexport.parseador.parse_decimal` al otro lado del proyecto.

### Verificación

| Puerta | Resultado |
|---|---|
| `tests/unit/test_parser_xlsx.py` (nuevo) | **31 passed** — forma, cadena de saldos, orden inverso, sin metadatos, fecha de Excel, cabecera sin tildes, IBAN, pie de totales; y los 7 rechazos (saldo roto, sin cabecera, sin movimientos, XLSX dañado, XLSX vacío, USD, fecha ilegible) |
| `tests/integration/test_importacion_xlsx.py` (nuevo) | **14 passed** — persistencia, signo e importe positivo (CHECK de la tabla), IBAN en la auditoría, cuenta obligatoria, cuenta inexistente, duplicado, descuadre sin dejar nada a medias, USD, aislamiento entre empresas, y 4 tests HTTP |
| `tests/unit/test_extracto_layouts.py` (nuevo) | **12 passed** — el desplegable y el catálogo dicen lo mismo, `accept` incluye `.xlsx`, la API acepta lo del catálogo y rechaza lo demás **diciendo lo que sí hay** |
| Fichero real `Data/*.xlsx` | Ejecutado el parser contra el fichero: 116 movimientos, del `2026-01-02` al `2026-02-27`, saldo inicial `1863,7400`, final `5281,9900`, IBAN detectado, orden cronológico y cuadre exacto. **No hay test que lo fije**, y no lo hay a propósito: el fichero es un extracto real y meterlo en el repositorio es un problema de datos personales. La forma sí la fijan 31 tests con un XLSX sintético de la misma plantilla |
| Suite completa (SQLite) | **3055 passed / 24 skipped**. El único fallo es el flaky conocido `test_suggest_perf` (una de las 9 iteraciones tardó 3,6 s en vez de los 500 ms del umbral, bajo carga), **2 passed** aislado. También falló `test_guard_siembra_empresa`, de forma real y por una razón distinta, ya corregido (ver «Un guard que ya existía cazó esto») |
| `tests/integration/test_pg_schema.py` (PostgreSQL real) | **20 passed** (antes 19) |
| **Aplicación real** (PostgreSQL 18.6, HTTP de verdad) | login 200 → `layout=xlsx` **422** con la lista de los válidos → sin cuenta **422** con el IBAN → import **201** con 116 movimientos → reimportar **409** → detalle 200 → abrir conciliación 201 → propuestas 200 → cerrar con diferencia ≠ 0 **409**. **Y la base queda como estaba**: 0 extractos, 0 movimientos, hash de la clave restaurado. Detalle en §3 |
| `ruff check src tests` | limpio |
| `mypy` | limpio, 416 fuentes |
| `tsc` / ESLint / `next build` | verdes, 92 páginas estáticas, 1 warning preexistente de `ContextZone`. Hubo que parar el `next dev` del 3000 antes del build y volver a levantarlo: las dos puertas escriben en el mismo `.next` |

#### Los cuatro guards se han visto fallar

Un guard que no se ha visto fallar no es un guard, es un comentario. Los cuatro se
comprobaron **reintroduciendo su defecto**:

| Guard reintroducido | Qué falla |
|---|---|
| Desplazamiento silencioso (todo lo desconocido cae en la norma 43) | 6 tests, uno por cada valor mal escrito |
| Se acepta un XLSX sin comprobar la cadena de saldos | `test_rechaza_un_saldo_que_no_encaja_con_los_importes` |
| Se acepta un extracto en USD | `test_rechaza_un_extracto_que_no_esta_en_euros` y `test_un_extracto_en_dolares_no_se_importa` |
| Sin opción `.xlsx` en el desplegable / sin `.xlsx` en el `accept` | 2 y 3 tests respectivamente |

#### Un guard que ya existía cazó esto

`test_guard_siembra_empresa::test_la_lista_de_pendientes_no_tiene_ficheros_inventados`
falló, y con razón. Al mover el fixture `recon_client` de
`tests/integration/test_conciliacion_http.py` a `conftest.py` (lo necesitaban también
los tests del XLSX), ese fichero dejó de construir `Company(` a mano y su entrada en
la lista `PENDIENTES` se quedó obsoleta. El guard existe exactamente para esto:
«una lista que miente deja de ser una cremalla». Se ha borrado la entrada, que es lo
que la lista permite hacer —**solo puede encogerse**— y se ha reutilizado
`sembrar_empresa_pgc` en el fixture nuevo.

---

## 2. Cambiar de empresa, de ejercicio y cerrar sesión

### Qué pasaba

En la parte de arriba se veían empresa, ejercicio y usuario, y:

- **Cambiar de empresa**: se podía, con el desplegable de la izquierda.
- **Cambiar de ejercicio**: se podía, con el desplegable de la izquierda.
- **Cerrar sesión**: **no existía en ninguna parte de la aplicación**.

Y el usuario no tenía ninguna acción: su nombre era un `<span>` de texto, sin botón.
Para cerrar sesión había que vaciar `localStorage` a mano.

### Qué se ha hecho

Nuevo componente `frontend/src/components/navigation/SessionMenu.tsx`, montado en
`ContextZone` **dos veces**: en la barra de escritorio (donde estaba el `<span>` del
usuario) y dentro de la hoja de compacto (el móvil), para que exista también allí.

El menú tiene:

- Cabecera con nombre, correo y rol.
- **Cambiar de empresa** → lista de las empresas del usuario, con NIF y la activa
  marcada. Con una sola empresa lo dice en vez de dejar un desplegable vacío.
- **Cambiar de ejercicio** → lista con año, **etiqueta de estado** (`cerrado`,
  `apertura`, `cerrando`) y número de asientos. Los cerrados salen deshabilitados con
  el motivo, como en el selector rápido.
- **Cerrar sesión** → borra la sesión y manda a `/login`.

Accesibilidad: `role="menu"` / `role="menuitem"` / `role="menuitemradio"` con
`aria-checked`, `aria-haspopup`, `aria-expanded`, cierre con `Escape` y al pulsar
fuera, y el foco vuelve al disparador.

#### Tres cosas que no son obvias y se han escrito en el código

**El orden del cierre de sesión.** `limpiarSesion()` borra la empresa activa de
`localStorage`. `setEjercicioActivo(null)` **solo puede borrar la entrada del mapa si
todavía sabe de qué empresa es**. Al revés, el ejercicio elegido se queda
guardado y el siguiente usuario de la misma máquina abre la aplicación en el
ejercicio que eligió el anterior. Hay un guard que fija el orden.

**La presentación del estado del ejercicio no se reimplementa.** FR-031 de SPEC-031
dice que el estado no puede depender solo del color. `etiqueta()` y `clase()` se
**exportan** de `ExerciseSwitcher.tsx` y el menú las importa. Dos copias de esa
regla se separan en cuanto una de las dos se toca.

**Lo que el menú NO hace**, y por qué: el cambio de empresa y de ejercicio se pide a
`useSesion().cambiarEmpresa` / `cambiarEjercicio`, no se escribe aquí. Esos saben
que hay que escribir el almacen **antes** de recargar, porque la cabecera
`X-Empresa-Activa` viaja con la propia petición que recarga. Reescribirlo en el menú
sería copiar el orden correcto en un sitio donde nadie lo documentaría.

**Los selectores rápidos no se han quitado.** `CompanySwitcher` y
`ExerciseSwitcher` siguen a la izquierda: son el camino rápido y llevan cosas que el
menú no puede abarcar (el contador de asientos, el atajo al ejercicio anterior
abierto, la explicación de por qué un cerrado no es seleccionable). El menú se
**añade**. Hay un guard que falla si desaparecen.

### Verificación

| Puerta | Resultado |
|---|---|
| `tests/unit/test_navegacion_menu_sesion.py` (nuevo) | **20 passed** — montaje en escritorio y compacto, las tres acciones, roles de menú, el orden del cierre de sesión, que la cookie también se borra, que se delega en el contexto de sesión, que se reutiliza `etiqueta`/`clase`, que los cerrados no son elegibles, y que los selectores rápidos siguen |
| `tsc` / ESLint / `next build` | verdes. El build compila, genera las 92 páginas estáticas y da 1 warning (el mismo de ESLint: `react-hooks/exhaustive-deps` en `ContextZone:85`, preexistente). **No se ha añadido ni quitado ninguna ruta.** Hubo que parar el `next dev` del 3000 antes de lanzarlo y volver a levantarlo después: las dos puertas pesadas escriben en el mismo `.next` y eso ya rompió el login una vez (§51 de `AGENTS.md`) |
| `next build` | verde: compila en 4,5 s, genera las 92 páginas estáticas, 1 warning (el mismo de ESLint). **No se ha añadido ni quitado ninguna ruta.** Hubo que parar el `next dev` del 3000 antes de lanzarlo y volver a levantarlo después, porque las dos puertas escriben en el mismo `.next` |

**Límite honesto de esta verificación**: estos tests **leen el fuente**, no ejecutan
React. El proyecto no tiene runner de tests de frontend y añadir uno (vitest +
jsdom + Testing Library) por tres reglas es más de lo que se ha pedido. Lo que sí
cubre un guard de fuente es lo que un guard de fuente cubre: que el componente esté
montado, que las acciones existan, y que el orden de las líneas sea el correcto. **Lo
que no cubre es que el menú se abra, se vea bien, y que el botón funcione.** Eso hay
que mirarlo en un navegador, y hasta entonces la afirmación honesta es «compila, está
montado y las reglas están escritas», no «funciona».

El menú **no se ha mirado en el navegador** en esta sesión. Los guards de montaje
existen precisamente porque en la auditoría de SPEC-031 (§51 de `AGENTS.md`) un
componente sin montar pasó `tsc`, ESLint y `next build` sin que nada lo dijera.

---

## 3. Las tablas de conciliación no existían en PostgreSQL

### Qué pasaba

SPEC-013 se cerró el 2026-09-19 con **54/54 tareas** y todas sus puertas en verde.
Aun así, `extracto_bancario`, `movimiento_bancario`, `conciliacion`,
`cruce_conciliacion`, `periodo_conciliado` y `alerta_conciliacion` **no existían en
la base de datos real**. Medido sobre PostgreSQL 18.6:

```
SELECT count(*) FROM information_schema.tables
 WHERE table_name IN ('extracto_bancario','movimiento_bancario', ...);   ->  0
```

Vivían solo en el `Base.metadata.create_all` que hace cada test de SQLite. En
producción, `POST /api/v1/extractos` respondía **500** con `UndefinedTableError`, y
toda la superficie de conciliación (`/conciliacion` y sus cuatro páginas) era
inservible. **El arreglo 1 no habría funcionado nunca.**

### Por qué no lo vio ninguna puerta

`test_migrations.py` comprueba que las migraciones **declaradas** estén en el
inventario, y que el orden por dependencias cuadre. No comprueba que cada tabla del
ORM tenga una. Un modelo sin migración es invisible para esa puerta: no está en el
inventario, así que no hay nada que faltar.

Lo agravó que en las 20 specs posteriores a SPEC-013 **cada una** añadiera su
migración, y que nadie notara que faltaba la de una spec anterior. La puerta de
migraciones grew sin que la deuda se acumulara visible.

### Qué se ha hecho

- **`backend/migrations/024_conciliacion.sql`**: 9 enums, las 6 tablas, 2 CHECK de
  cuadre (`diferencia = saldo_banco - saldo_libros` y `diferencia = 0`), 5 FKs
  compuestas por `empresa_id`, unicidad de `sha256` por empresa (la deduplicación de
  la importación hecha a nivel de esquema, no solo en el servicio), y 4 triggers.
- Registrada en `db/migrate.py::ORDEN_PREFERENTE` y en
  `test_migrations.py::ESPERADAS`, y añadida al conjunto `TABLAS_ESPERADAS` de los
  contratos de PostgreSQL.
- Aplicada sobre la base real: `db.migrate` **24/24**, y la segunda pasada no hace
  nada (idempotente, verificado).

#### El trigger que casi rompe la conciliación

La primera versión hacía `movimiento_bancario` **append-only**, rechazando cualquier
`UPDATE`. Eso es exactamente lo que está mal, y ningun test de SQLite lo cazó
porque allí esas tablas no tienen trigger. Aparece en la lista de columnas
inmutables del propio SQL, y un guard lo fija ahora.
porque allí la inmutabilidad de estas tablas no está implementada (no hay triggers
SQLite para conciliación).

El motivo: `services/reconciliation/cruce.py:129` hace
`mov.estado = EstadoMovimiento.conciliado` al confirmar un cruce, y la línea 173 lo
devuelve a `pendiente` al deshacerlo. Un trigger que reventase el `UPDATE` entero
habría hecho la conciliación **inservible**, que es justo su función. Se detectó al
leer la respuesta del `DELETE` en la prueba de humo, no al escribir el SQL.

El trigger definitivo compara **columna a columna**: `importe`, `signo`, `fecha_*`,
`concepto`, `referencia`, `orden` y `extracto_id` no se tocan; `estado` sí, porque es
una columna de flujo de trabajo, no contenido del banco. Hay un guard que fija
exactamente qué columnas compara y que `estado` **no** está entre ellas.

#### Verificación en PostgreSQL real

| Comprobación | Resultado |
|---|---|
| Las 6 tablas existen | sí, tras `db.migrate` 24/24 |
| `test_pg_schema.py` | **20 passed** (antes 19; +1 contrato nuevo) |
| `UPDATE ... SET estado` | **permitido** — es lo que hace confirmar y deshacer un cruce |
| `UPDATE` de `importe` / `signo` / `concepto` / `fecha_operacion` | **rechazado**, con el mensaje «inmutable» |
| `DELETE` de un movimiento | **rechazado** |
| `periodo_conciliado` UPDATE y DELETE | **rechazados** (append-only entero) |
| `importe <= 0` | **rechazado** por el CHECK |
| `sha256` repetida en la misma empresa | **rechazada** por el UNIQUE |

#### La puerta que faltaba, y que es lo que de verdad cuenta

Cinco guards nuevos en `test_migrations.py`, y **los cinco se han visto fallar**
reintroduciendo su defecto:

| Defecto reintroducido | Qué falla |
|---|---|
| La migración no crea `movimiento_bancario` | `test_toda_tabla_del_orm_tiene_migracion` y `test_la_migracion_de_conciliacion_crea_las_seis_tablas` |
| Un modelo nuevo en `src/models/` sin migración | `test_toda_tabla_del_orm_tiene_migracion` |
| El trigger vuelve a reventar cualquier `UPDATE` | `test_la_migracion_de_conciliacion_admite_cruzar_un_movimiento` |
| `ADD CONSTRAINT` sin la guardia de idempotencia | `test_las_migraciones_son_idempotentes_tras_aplicadas` |
| 024 fuera de `ORDEN_PREFERENTE` | `test_el_inventario_coincide_con_orden_preferente` |

La importante es la primera: **`test_toda_tabla_del_orm_tiene_migracion` cruza los
`__tablename__` de `src/models/` con los `CREATE TABLE` de `migrations/`**. Con eso,
la clase de defecto «un modelo nuevo sin migración» es la primera que se ve, y
`test_migraciones_crean_tablas` de PostgreSQL deja de necesitar una base limpia para
detectar un fichero borrado.

**Y un límite honesto de ese guard**: cuando se le quitó el fichero `024` de disco,
`test_migraciones_crean_tablas` de PostgreSQL **no** falló, porque el fixture
`pg_engine` aplica las migraciones sobre la base de verdad sin borrar el esquema, y
las tablas seguían ahí de la pasada anterior. Solo fallaron los tres guards de
fichero. Por eso el guard nuevo mira el código en vez de la base: es el que no depende
de en qué estado esté la base.

#### Deuda que este guard ha destapado, y que **no** se ha pagado

`test_toda_tabla_del_orm_tiene_migracion` inventarió las tablas del ORM sin
migración. Salen **27**, de SPEC-005/007/008/010/011/012/014/020:

```
activo_inmovilizado          amortizacion_generada      baja_activo
blob_fichero                 clasificacion_efe          cobro_conciliado
cobro_pago                   condicion_pronto_pago      configuracion_informe
configuracion_sii            devolucion_recibo          exportacion_modelo
factura                      factura_linea              formulacion_cuentas_anuales
iva_diferido_caja            mandato_sepa               periodo_fiscal
plan_amortizacion            recibo_remesa              reclamacion
remesa                       secuencia_remesa           serie_factura
tercero                      tercero_subcuenta          vencimiento
```

**No se han migrado.** Facturación, terceros, remesas SEPA, inmovilizado y los libros
de IVA son features enteras, y migrarlas es trabajo de un día por spec, no un
apéndice de esta corrección. Lo que **sí** se ha hecho es poner la lista en
`TABLAS_SIN_MIGRACION`, con dos guards que obligan a que la lista **no mienta** en
ninguna de las dos direcciones:

- `test_la_lista_de_tablas_sin_migracion_no_miente`: si una tabla de la lista ya
  tiene migración, hay que borrarla de la lista.
- `test_la_lista_de_tablas_sin_migracion_no_nombra_tablas_inventadas`: si la lista
  nombra una tabla que ya no está en los modelos, hay que borrarla.

Es el mismo patrón que `PENDIENTES` en `test_guard_siembra_empresa`, y por el mismo
motivo: **una lista de deuda que nadie audita deja de ser una lista en el momento en
que alguien mueve un fichero**. La lista solo puede encogerse.

**Consecuencia para el usuario, dicha con todas sus letras**: si en la aplicación
real se importan facturas, remesas, vencimientos o inmovilizado, eso **también**
devolverá 500, por el mismo motivo y desde hace tiempo. Lo del arreglo 3 solo
devuelve la conciliación. Las demás son la entrada 1 de la §4.

---

## 4. Lo que queda pendiente, y por qué no se ha hecho

| # | Pendiente | Por qué no se ha hecho |
|---|---|---|
| 1 | **Las 27 tablas del ORM sin migración** (facturas, terceros, vencimientos, remesas SEPA, inmovilizado, libros de IVA…) | Es el arreglo 3 aplicado a features enteras: migración por migración, un día por spec. Inventariadas y guardadas por `TABLAS_SIN_MIGRACION` (§3). **Es lo más urgente de esta lista**: son 500 en la aplicación real. |
| 2 | **Persistir el IBAN** en `extracto_bancario` (columna + migración) | Ahora solo vive en el `payload` de la auditoría. Es un cambio de esquema para algo que nadie ha pedido todavía. |
| 3 | **Maestro IBAN → cuenta 572** | Sin él, el usuario teclea `5720` cada vez. Es una feature con su propia spec (altas, bajas, validación, un IBAN por cuenta y cuenta por IBAN). |
| 4 | **`POST /logout` en el backend** | Hoy «salir» es borrar credenciales en el cliente. El token expira solo en 30 min (`ACCESS_TOKEN_EXPIRE_MINUTES`), pero no hay lista de revocación: un token robado sigue valiendo hasta expirar. No es lo que se pidió y es un cambio de seguridad. |
| 5 | **El hash de la clave de `admin@contabilidad.es` en `023_seed_demo.sql` no corresponde a `admin123`** | Detectado al intentar iniciar sesión con las credenciales que documenta el propio seed. El hash es de 60 caracteres (bien formado) y `bcrypt.checkpw('admin123', hash)` devuelve `False`, así que **el usuario de demo no se puede identificar con la clave que el comentario del seed dice**. Preexistente de §46. Corregirlo es tocar una migración ya aplicada, y §50 avisa de que eso obliga a que siga siendo idempotente: lo propio es una migración nueva que corrija la fila. No se ha hecho porque es un cambio de credenciales y no se ha pedido. |
| 6 | **Límite de tamaño en `POST /api/v1/extractos`** | El endpoint hace `await file.read()` sin tope, y ahora admite un XLSX (binario, potencialmente más grande que un `.txt`). `api/importexport.py` sí tiene `MAX_BYTES = 5 MB`. Preexistente, no lo introduce esta corrección, pero el XLSX lo hace más fácil de alcanzar. |
| 7 | **Runner de tests de frontend** | Ver el límite de §2. Con él, los 20 guards de fuente se sustituyen por unos que montan el componente. |
| 8 | **`extracto_43_19_duplicado.txt` es un fixture huérfano** | Nadie lo referencia. La detección de solapamiento (mismo rango, saldos y número de movimientos con `sha256` distinto) no tiene test. Preexistente. |
| 9 | **El fixture `pg_engine` aplica migraciones sobre la base real sin borrar el esquema** | Por eso `test_migraciones_crean_tablas` no detecta un fichero de migración borrado si la base ya tiene las tablas. El guard nuevo de §3 mira el código y no depende del estado de la base, pero el fixture sigue siendo lo que es. Arreglarlo (borrar el esquema al empezar) cambiaría el comportamiento de los otros 19 contratos. |

## 5. Specs a corregir cuando se apruebe

### SPEC-013 · Conciliación bancaria

Es la spec más afectada: le cambian el formato admitido, la API y le faltaba la
migración que debiera haber tenido desde el día uno.

- **`tasks.md`, y es lo más grave**: las 54 tareas marcadas no incluyen ninguna
  migración. La spec se dio por cerrada con la conciliación **inservible en la
  aplicación real**. Hay que añadir las tareas de la migración 024 y marcarlas, o la
  spec vuelve a mentir sobre su propio estado.
- `research.md` líneas 10–12: la decisión «**UE: formato XLSX/qif desestimados por no
  estar en la spec**» y el `NEEDS CLARIFICATION` quedan **resueltos**: XLSX sí.
- `spec.md` línea 105 («formato interoperable (CSV/XLSX según norma 43/19)»): era una
  afirmación que la implementación no cumplía. Ahora sí, con `xlsx_bancario` como
  tercer formato y no como sinónimos de la norma 43.
- `contracts/api-contracts.md`: documentar el tercer valor de `layout`, el 422
  `layout_desconocido` con su lista, y el 422 `divisa_no_soportada`. El contrato
  menciona un `concepto_norma` de formulario que **no está implementado**.
- `data-model.md`: `ExtractoDTO` no está (es un DTO de servicio, no una tabla), pero
  sí habría que decidir lo del IBAN del punto 2 de §4.
- `tasks.md`: añadir las tareas de esta corrección. Las existentes **no** hablan nada de XLSX, porque el formato se desestimó en research.

- Renumerar la lista de layouts en cualquier sitio donde se escriba «dos formatos».

### SPEC-031 · Navegación y superficies

- `spec.md` FR-002 (zona de contexto): ahora incluye un menú de sesión con cambiar
  empresa, cambiar ejercicio y cerrar sesión. Es una capacidad que **no** está en la
  spec, y es justo el tipo de cosa que la spec tenía que haber fijado: FR-002 habla de
  «identidad, empresa y ejercicio» como *información*, no como *acciones*.
- `quickstart.md`: añadir el recorrido de cerrar sesión y de cambiar de empresa desde
  el menú, a los diez escenarios que ya hay.
- `tasks.md`: las tareas del menú.

### SPEC-003 · Multiempresa RBAC

- La spec define login, `me`, switch de empresa y alta/listado de empresas. **No**
  define ningún cierre de sesión, porque no existía. Si se decide el punto 3 de §4
  (revocación en el backend), esta es la spec que lo recoge.

### Mención en `AGENTS.md`

Hay que añadir una sección al final con el estado de esta sesión, siguiendo la
estructura de las §42–§51. En particular, la lección reutilizable que más ha
rentado de este trabajo, y que es la misma de §51 pero aplicada a otra puerta:

> **Una puerta que compara el inventario con lo declarado no ve lo que falta.**
> `test_migrations.py` comprueba que las migraciones *declaradas* estén listadas, y
> por eso SPEC-013 pudo cerrarse con 54/54 tareas, sus puertas en verde y **sus seis
> tablas sin existir en PostgreSQL**. Un modelo sin migración no está en el
> inventario, así que no hay nada que faltar. La puerta que faltaba cruza los
> `__tablename__` de `src/models/` con los `CREATE TABLE` de `migrations/`, y esa
> es la que habría distinto.

Las otras dos que merece la pena:

> **Una puerta verde no dice que la cosa funcione en la aplicación.** Todo el arreglo
> del XLSX pasó `pytest`, `ruff`, `mypy`, `tsc`, ESLint y `next build` antes de
> descubrir que en la aplicación real devolvía 500. Lo que faltaba era una prueba
> contra el PostgreSQL de verdad, y esa es la que destapó el defecto.

> **Un trigger de inmutabilidad que no se ha ejecutado contra el código que
> protege, se equivoca.** `movimiento_bancario` append-only habría roto confirmar y
> deshacer un cruce —su función entera— y ningún test de SQLite lo habría visto,
> porque allí esas tablas no tienen trigger. Aparece en la lista de columnas
> inmutables del propio SQL, y un guard lo fija ahora.

