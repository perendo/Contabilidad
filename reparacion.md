# Las 27 tablas que faltan, y por qué se rompen

**Fecha**: 2026-09-29 | **Spec que lo resuelve**: ninguna. `specs/032-completar-migraciones/`
se creó y se borró: el usuario decidió repararlas sin una spec nueva.
**Lista de referencia**: [`backend/tests/esquema_deuda.py`](backend/tests/esquema_deuda.py)

> **ESTADO FINAL: las 27 están migradas. La deuda de tablas es `set()`.**
>
> Este fichero se conserva por dos razones: porque explica un modo de fallo que le costó
> seis meses al proyecto (una puerta que compara migraciones *declaradas* no ve un modelo
> sin migración), y porque dice qué se encontró por el camino que no estaba en el encargo.
> Lo que queda abierto esta al final, y son tres cosas de **diseño**, no de esquema.

---

## Resultado

| Fichero | Tablas | Spec | Estado |
|---|---|---|---|
| `025_prevision_plan_manual.sql` | — (una columna) | SPEC-027 | aplicada |
| `026_manifiesto_n_bloques.sql` | — (un default) | SPEC-029 | aplicada |
| `027_maestros_comerciales.sql` | 5 | SPEC-007, SPEC-008 | aplicada |
| `028_cobros_vencimientos.sql` | 2 | SPEC-011 | aplicada |
| `029_remesas_complemento.sql` | 9 | SPEC-020 | aplicada |
| `030_inmovilizado_completo.sql` | 4 | SPEC-014 | aplicada |
| `031_informes_iva.sql` | 7 | SPEC-010, SPEC-012 | aplicada |

**32 migraciones aplicadas.** El ORM declara 109 tablas y la base tiene 110: las 109 más
`schema_migrations`, que es la tabla de control del propio runner. El comparador de
esquema da **0 diferencias reales** y 122 equivalentes (que no lo son: son la misma cosa
escrita de dos maneras, como `VARCHAR(64)` contra `CHAR(64)` o un `DEFAULT 0.0000` contra
un `DEFAULT 0`).

Además del trabajo pedido, salió esto:

| Hallazgo | Qué era | Dónde está el guard |
|---|---|---|
| `plan_manual` no existía | Toda la previsión de tesorería devolvía 500 | `test_toda_tabla_del_orm_tiene_migracion` |
| **Colisión de enums** (2 pares) | `periodo_fiscal` y `exportacion_modelo` eran **inmigrables** | `test_no_hay_dos_enums_con_el_mismo_nombre_y_valores_distintos` |
| **Nombres de restricción duplicados** (5 tablas) | La mitad de SPEC-020 era **inmigrable** | `test_no_hay_dos_restricciones_con_el_mismo_nombre` |
| `n_bloques` sin default | Un `INSERT` a mano fallaba | `test_el_esquema_no_se_aparta_de_los_modelos` |
| `evento_auditoria_acceso.rol_id` → `roles.id` | FK ciega al tenant, preexistente | `FK_CIEGAS_AL_TENANT` |

Los dos hallazgos de enums y de restricciones son **la misma clase de defecto**:
**SQLite es más permisivo que PostgreSQL y todo el esquema del proyecto se ha verificado
siempre contra SQLite**. Ninguno se podía ver leyendo el código; los dos aparecieron al
escribir el `CREATE TABLE`.

---



---

## La causa, que es una sola y se explica una vez

Las 27 tablas **no están mal definidas**. Sus modelos existen, están completos, tienen
sus restricciones y sus tipos correctos. Lo que no existe es el fichero de migración
que las crea.

Las pruebas del repositorio construyen el esquema **directamente desde los modelos**, no
desde las migraciones. Por eso siempre han pasado: el test levanta sus propias tablas y
nunca ha mirado si la base de datos real las tiene.

Cuando la aplicación se ejecuta contra la base de verdad y una consulta toca una tabla
que no existe, PostgreSQL responde `UndefinedTableError`, la capa de datos lo traduce a
**HTTP 500**, y la pantalla se queda en blanco. No es un error de validación ni de
permisos: es que la tabla no está.

### Por qué ninguna puerta lo detectó

`test_migrations.py` comprobaba que las migraciones **declaradas** estuvieran listadas,
y que el orden por dependencias cuadrara. Nunca comprobó que **cada tabla que la
aplicación declara tuviera una migración**. Un modelo sin migración no aparece en el
inventario, así que no había nada que faltara en la comprobación.

El caso más grave: **la conciliación bancaria se cerró con 54/54 tareas**, pasó `ruff`,
`mypy`, el typecheck, el lint y la compilación del frontend, y aun así
`POST /api/v1/extractos` devolvía 500. Sus 6 tablas tampoco tenían migración. Se
descubrió el 2026-09-29 al probar contra PostgreSQL de verdad, no al leer el código.

La puerta que faltaba ya está escrita: `test_toda_tabla_del_orm_tiene_migracion` cruza
los `__tablename__` de `src/models/` con los `CREATE TABLE` de `migrations/`. Inventarió
estas 27.

### Cómo se comprueba una de estas roturas

```
GET /api/v1/terceros        -> 500
```

En los logs del backend, por encima de la respuesta:

```
UndefinedTableError: relation "tercero" does not exist
```

Si el mensaje es ese, es una de las 27. Si es `403`, es un problema de empresa activa y
no tiene nada que ver con esto.

---

## Las 27, agrupadas por la spec que las definió

Cinco grupos. **No hay ninguna dependencia entre ellos**: cada tabla depende, cuando
depende, de otra de su propio grupo. Por eso se pueden migrar en cualquier orden.

### Grupo 1 · Maestros comerciales y facturación — 5 tablas
**Specs**: SPEC-008 (terceros) + SPEC-007 (facturación) · **Orden interno**: 0 → 1 → 2

| Tabla | Modelo | Depende de (entre las 27) |
|---|---|---|
| `tercero` | `ar/tercero.py` | — |
| `tercero_subcuenta` | `ar/tercero_subcuenta.py` | — |
| `serie_factura` | `invoice/serie_factura.py` | — |
| `factura` | `invoice/factura.py` | `serie_factura`, `tercero` |
| `factura_linea` | `invoice/factura_linea.py` | `factura` |

**Qué se rompe**: el maestro de terceros entero (alta, consulta, baja, cambio de NIF,
retirada) y toda la facturación (series, borradores, emisión, rectificación, anulación,
borrado).

**Endpoints que devuelven 500**:
```
GET    /api/v1/terceros                    GET    /api/v1/terceros/{tercero_id}
POST   /api/v1/terceros                    PATCH  /api/v1/terceros/{tercero_id}/nif
POST   /api/v1/terceros/{tercero_id}/retirar
DELETE /api/v1/terceros/{tercero_id}
POST   /api/v1/terceros/{tercero_id}/mandatos      (mandato_sepa)
GET    /api/v1/terceros/{tercero_id}/condiciones   (condicion_pronto_pago)
POST   /api/v1/facturacion/series           PATCH  /api/v1/facturacion/series/{serie_id}/estado
POST   /api/v1/facturacion/facturas         GET    /api/v1/facturacion/facturas/{factura_id}
POST   /api/v1/facturacion/facturas/{factura_id}/emitir
POST   /api/v1/facturacion/facturas/{factura_id}/anular
POST   /api/v1/facturacion/facturas/{factura_id}/rectificar
DELETE /api/v1/facturacion/facturas/{factura_id}
```

**⚠️ Arrastra dos de remesas**: `mandato_sepa` y `condicion_pronto_pago` se gestionan
desde la pantalla de terceros (`POST /terceros/{id}/mandatos`). Si esa pantalla no
funciona, no es solo por `tercero`.

**Es el grupo más caro en datos y el más consultado.** Siete de las 27 cuelgan de él, y
por eso fija el orden de casi todo lo demás.

---

### Grupo 2 · Cobros y vencimientos — 2 tablas
**Spec**: SPEC-011 · **Orden interno**: todo en nivel 0, se puede escribir de una vez

| Tabla | Modelo | Depende de (entre las 27) |
|---|---|---|
| `vencimiento` | `ar/vencimiento.py` | — |
| `cobro_pago` | `treasury/cobro_pago.py` | — |

**Qué se rompe**: la pantalla de vencimientos, los cobros, los pagos y la antigüedad.

**Endpoints que devuelven 500**:
```
GET    /api/v1/vencimientos/{vencimiento_id}
POST   /api/v1/vencimientos/{vencimiento_id}/cobrar
POST   /api/v1/vencimientos/{vencimiento_id}/pagar
GET    /api/v1/vencimientos/{vencimiento_id}/cobros
```

**⚠️ Ojo con esta**: `vencimiento` declara `factura_id` y `tercero_id` como **columna
UUID suelta, sin clave foránea**. No hay dependencia real en la base, pero sí en la
lógica: un vencimiento sin factura es un huérfano que el servicio no contempla. Al
migrarla hay que decidir si se declara esa clave foránea o no (es la **Decisión 1** del
plan).

---

### Grupo 3 · Remesas SEPA — 9 tablas
**Spec**: SPEC-020 · **Orden interno**: 0 → 1 → 2 → 3, cuatro niveles

| Tabla | Modelo | Depende de (entre las 27) |
|---|---|---|
| `secuencia_remesa` | `treasury/secuencia_remesa.py` | — |
| `mandato_sepa` | `treasury/mandato_sepa.py` | — |
| `condicion_pronto_pago` | `treasury/condicion_pronto_pago.py` | — |
| `remesa` | `treasury/remesa.py` | — |
| `blob_fichero` | `treasury/blob_fichero.py` | — |
| `recibo_remesa` | `treasury/recibo_remesa.py` | `remesa` |
| `devolucion_recibo` | `treasury/devolucion.py` | `recibo_remesa` |
| `reclamacion` | `treasury/devolucion.py` | `devolucion_recibo` |
| `cobro_conciliado` | `treasury/cobro_conciliado.py` | `recibo_remesa` |

**Qué se rompe**: toda la superficie de remesas, incluidos painless, cesión de cobros,
antigüedad, devoluciones y reclamaciones. Nueve tablas de golpe: es el grupo más grande
con diferencia.

**Endpoints que devuelven 500**:
```
GET    /api/v1/remesas
POST   /api/v1/remesas                      GET    /api/v1/remesas/{remesa_id}
POST   /api/v1/remesas/{remesa_id}/emitir
GET    /api/v1/remesas/{remesa_id}/fichero
POST   /api/v1/remesas/{remesa_id}/recibos/{recibo_id}/cobrar
POST   /api/v1/remesas/{remesa_id}/recibos/{recibo_id}/conciliar
POST   /api/v1/devoluciones/import
GET    /api/v1/devoluciones/{devolucion_id}
POST   /api/v1/devoluciones/{devolucion_id}/reclamaciones
```

**⚠️ Dos advertencias**:
- `blob_fichero` y `cobro_conciliado` son **acoplamientos con SPEC-013**, que ya tiene
  migración (`024_conciliacion.sql`). `cobro_conciliado` tiene además clave foránea a
  `recibo_remesa`, que no existe hasta que se migre este grupo. Decisión 3 del plan: en
  su propio fichero, y **sin tocar la 024**, que ya está aplicada.
- Este grupo es donde **ya falló un trigger**: el primer intento de proteger
  `movimiento_bancario` lo volvió inmodificable e impedía confirmar y deshacer un cruce,
  que es la función entera de la conciliación. Ninguna prueba de SQLite lo habría visto.

---

### Grupo 4 · Inmovilizado — 4 tablas
**Spec**: SPEC-014 · **Orden interno**: 0 → 1

| Tabla | Modelo | Depende de (entre las 27) |
|---|---|---|
| `activo_inmovilizado` | `inmovilizado/activo.py` | — |
| `plan_amortizacion` | `inmovilizado/plan_amortizacion.py` | `activo_inmovilizado` |
| `amortizacion_generada` | `inmovilizado/amortizacion_generada.py` | `activo_inmovilizado` |
| `baja_activo` | `inmovilizado/baja_activo.py` | `activo_inmovilizado` |

**Qué se rompe**: el alta de inmovilizados, el cálculo del plan, la generación de
amortizaciones y las bajas.

**Endpoints que devuelven 500**:
```
POST   /api/v1/activos                      GET    /api/v1/activos/{activo_id}
PATCH  /api/v1/activos/{activo_id}          POST   /api/v1/activos/{activo_id}/baja
POST   /api/v1/activos/plan/calcular         POST   /api/v1/activos/{activo_id}/plan/calcular
GET    /api/v1/amortizaciones/activos/{activo_id}
POST   /api/v1/amortizaciones/generar
POST   /api/v1/amortizaciones/{amortizacion_id}/reabrir
```

**El único grupo sin ninguna dependencia con los demás.** Se puede hacer entero y
verificarlo sin tocar nada más. Es también la feature que menos se usa, así que es la
candidata a recortarse si hubiera que recortar.

---

### Las claves foráneas: decisión tomada el 2026-09-29

**Se migran los modelos tal cual, sin añadir claves foráneas que el ORM no declara**, y
las referencias sueltas quedan anotadas como deuda con nombre en
[`tests/esquema_deuda.py`](backend/tests/esquema_deuda.py) (`REFERENCIAS_SIN_FK`).

**Son 51, no 22.** La primera cuenta dio 22, que son las que se van a crear. Al escribir el
guard sobre todo el ORM salieron **29 más en tablas cuya migración ya estaba escrita y
aplicada**: `journal_entry.original_id`, `fiscal_year.cierre_entry_id`,
`extracto_bancario.cuenta_id`, `conciliacion.cuenta_id`, `efecto.tercero_id`,
`centros de coste.subvencion_id`… Es un patrón heredado de las primeras specs, no algo de
estas 27, y por eso la lista es entera: anotarla a medias daría la impresión de que el
problema está acotado a un grupo de trabajo.

**Por qué no se añaden**:

- Una FK que el ORM no conoce puede convertir en **500 un `INSERT` que hoy funciona**, y no
  hay forma de saber cuáles sin revisar los servicios uno a uno. El riesgo es
  asimetrico: la FK da integridad en la base y cuesta disponibilidad.
- La constitución III **ya se cumple donde importa**: toda consulta pasa por
  `Depends(get_empresa_id)` y filtra por `empresa_id`. Hay tests de aislamiento
  cross-empresa para cada endpoint. Lo que la FK daría es integridad referencial *en la
  base*, que es una garantía distinta y más fuerte, y merece su propio análisis.

**Lo que sí es una FK ciega al tenant, y se encontró aquí**: hay **19 FKs de una sola
columna** en el ORM, y la mayoría son correctas (`empresa_id -> companies.id`,
`user_id -> users.id`, `permiso_id -> permiso_operacion.id` apuntan a tablas sin dimensión de
empresa, donde una columna basta). El criterio correcto no es el ancho sino si la tabla
destino tiene `empresa_id`. Aplicado ese criterio queda **una**:

| Columna | Destino | Por qué se queda |
|---|---|---|
| `evento_auditoria_acceso.rol_id` | `roles.id` (SPEC-015, `007_rbac.sql`) | Ya aplicada. Corregirla exige cambiar el modelo y una migración nueva sobre otra aplicada. La auditoría es de solo lectura, así que no permite escribir: el riesgo es de lectura, no de integridad |

Anotada en `FK_CIEGAS_AL_TENANT`, que también **solo puede encogerse**. La buena noticia es
que `factura.factura_original_id` **sí** es compuesta (`empresa_id`, `factura_original_id`),
así que el encadenamiento de rectificativas no es un hueco. Parecia un hueco al leer el
volcado, que solo enseñaba la primera columna de cada constraint.

---

**Specs**: SPEC-010 (cuentas anuales) + SPEC-012 (IVA) · **Orden interno**: todo en
nivel 0, se puede escribir de una vez

| Tabla | Modelo | Depende de (entre las 27) |
|---|---|---|
| `configuracion_informe` | `reporting/configuracion.py` | — |
| `formulacion_cuentas_anuales` | `reporting/formulacion.py` | — |
| `clasificacion_efe` | `reporting/control_efe.py` | — |
| `periodo_fiscal` | `fiscal/periodo_fiscal.py` | — |
| `exportacion_modelo` | `fiscal/exportacion_modelo.py` | — |
| `configuracion_sii` | `fiscal/configuracion_sii.py` | — |
| `iva_diferido_caja` | `fiscal/iva_diferido_caja.py` | — |

**Qué se rompe**: las cuentas anuales (balance, PyG, EFE, formulación y anulación), los
libros de IVA, los modelos 303/347/349, la exportación de modelos y el régimen de
criterio de caja.

**Endpoints que devuelven 500**:
```
GET    /api/v1/cuentas-anuales/{ejercicio}/balance
GET    /api/v1/cuentas-anuales/{ejercicio}/pyg
GET    /api/v1/cuentas-anuales/{ejercicio}/efe
PATCH  /api/v1/cuentas-anuales/{ejercicio}/efe/clasificacion
POST   /api/v1/cuentas-anuales/{ejercicio}/formular
POST   /api/v1/cuentas-anuales/{ejercicio}/anular-formulacion
GET    /api/v1/cuentas-anuales/{ejercicio}/formulaciones
POST   /api/v1/cuentas-anuales/configuracion   PATCH /api/v1/cuentas-anuales/configuracion
GET    /api/v1/libros-iva/{tipo_libro}
GET    /api/v1/modelos/303   GET /api/v1/modelos/347   GET /api/v1/modelos/349
GET    /api/v1/sii/configuracion               POST /api/v1/sii/configuracion
POST   /api/v1/regimenes/criterio-caja         GET  /api/v1/regimenes/estado
```

**⚠️ Un efecto lateral que no es evidente**: `periodo_fiscal` y
`formulacion_cuentas_anuales` se usan desde
`services/navigation/resumenes.py`, que alimenta `GET /api/v1/resumenes/{superficie}`.
Es decir, **los resúmenes de superficie de las seis secciones de la aplicación** tocan
una tabla que no existe. Eso puede explicar que algunos paneles de la navegación se
vean incompletos sin que se note por qué.

**⚠️ `configuracion_sii` está duplicada**: convive con la `ConfigSii` de SPEC-029, que
**sí** tiene migración (`020_export.sql`). Dos tablas para lo mismo. Es una decisión de
diseño, no de migración (**Decisión 2** del plan).

### La colisión de nombres de ENUM, y por qué la tenía que ver alguien

**Este es el hallazgo que sale de preparar la migración del grupo 5**, y no de leer el
código. En PostgreSQL un `SqlEnum` se materializa como un **tipo con nombre**, y un tipo
se define una sola vez. Hay dos pares de enums que se llaman igual y **valores distintos**:

| Nombre del tipo | Tabla que ya lo tiene (migrada) | Tabla que lo pide (sin migrar) |
|---|---|---|
| `estado_periodo` | `periodo_cerrado` — `abierto`, `cerrado`, `reabierto_ajuste`, `cerrado_ajustado` (SPEC-028) | `periodo_fiscal` — `pendiente`, `libros_generados`, `calculado_303`, `exportado` (SPEC-012) |
| `estado_exportacion` | `exportacion` — `en_proceso`, `lista`, `fallida` (SPEC-029) | `exportacion_modelo` — `generado`, `regenerado`, `anulado` (SPEC-012) |

**Corregido** en los dos modelos, con el sufijo en el `name=` del `SqlEnum`:
`estado_periodo_fiscal` y `estado_exportacion_modelo`. Es el mismo remedy que ya aplicaba
`models/budget/periodo_seguimiento.py` con `periodo_seguimiento_estado`: **el nombre de la
clase puede ser genérico, el del tipo no**. Se renombra la tabla que aún no está migrada, de
modo que ninguna migración aplicada cambia.

`tipo_periodo` sí lo comparten `periodo_cerrado` y `periodo_fiscal`, y está bien: los
**mismos** dos valores (`MES`, `TRIMESTRE`), solo que en orden distinto. El orden de un enum
solo afecta a `ORDER BY`, y el modelo manda el valor por texto.

**Por qué nadie lo había visto en 31 specs**: SQLite no tiene ENUM. Cada columna se
convierte en un `VARCHAR` con su propio `CHECK`, así que dos enums homónimos funcionan sin
problema y las 31 specs pasan sus puertas. La colisión **solo aparece al escribir el
`CREATE TYPE`**, es decir, en el momento exacto en que la tabla deja de estar de prueba.
Guard: `test_no_hay_dos_enums_con_el_mismo_nombre_y_valores_distintos`, comprobado
deshaciendo el renombrado.

---

## Recuento y orden

| Nivel | Tablas | Grupos que los contienen |
|---|---|---|
| 0 | 18 | todos |
| 1 | 5 | facturación, remesas, inmovilizado |
| 2 | 3 | facturación, remesas |
| 3 | 1 | remesas |

| Fichero de migración | Estado |
|---|---|
| `026_manifiesto_n_bloques.sql` | hecha |
| `027_maestros_comerciales.sql` | hecha 2026-09-29 |
| `028_cobros_vencimientos.sql` | hecha 2026-09-29 |
| `029_remesas_complemento.sql` | hecha 2026-09-29 |
| `030_inmovilizado_completo.sql` | hecha 2026-09-29 |
| `031_informes_iva.sql` | hecha 2026-09-29 |

⚠️ El desplazamiento desde `025`/`026` es porque `025_prevision_plan_manual.sql` ya estaba
aplicada, y añadir una migración nueva **arriba** de una aplicada es lo que rompe
`db.migrate` al reaplicar. `026` es una línea suelta que hace que modelo y esquema
coincidan en `manifiesto_exportacion.n_bloques`: el modelo declara `default=0` y
`020_export.sql` creó la columna sin defecto. No rompe nada (SQLAlchemy aplica el valor
en el cliente), pero un `INSERT` escrito a mano contra la tabla sí fallaría.

**No se editó `020_export.sql` para arreglarlo**, y esa es la parte importante: ya está
aplicada, y editarla no la deshace. `db.migrate` la reaplicaría y reventaría, y la base
quedaría en un estado que nadie sabe reconstruir. Una corrección al esquema de algo ya
aplicado va en una migración nueva, por pequeña que sea.

### Cómo se verificó el grupo 1

`test_esquema_completo.py` comprueba que las 5 tablas existen y coinciden con el modelo.
Eso **no** dice que las restricciones muerdan, así que hay un segundo contrato,
`tests/integration/test_pg_comerciales.py` (15 tests), que las quita de verdad una a una:

| Restricción que se quitó de la base | Test que lo detecta |
|---|---|
| `fk_factura_serie` (FK compuesta) | `test_una_factura_no_puede_colgar_de_la_serie_de_otra_empresa` |
| `chk_tercero_al_menos_un_rol` | `test_un_tercero_tiene_que_ser_cliente_o_proveedor` |
| `uq_factura_serie_ejercicio_numero` | `test_no_hay_dos_facturas_con_el_mismo_numero_de_serie` |

Las tres fallan al reintroducir el defecto, y la suite entera pasa al volver a ponerlas.
El contrato también prueba **el caso bueno** de cada restricción (una rectificativa de la
misma empresa sí entra, un tercero que es cliente y proveedor sí entra, tres borradores
sin `numero` no chocan entre sí), porque una FK que rechazase todo también pasaría los
tests de rechazo.

Dos cosas que salieron al escribir ese contrato y que se indebtedness aquí:

- **Un tipo de enum inválido no es un `IntegrityError`.** PostgreSQL lanza
  `DataError` / `InvalidTextRepresentationError` (SQLSTATE `22P02`). La primera versión
  solo recogía `IntegrityError` y dio por hecho que la tabla no rechazaba `'TRASPASO'`
  cuando sí lo hacía.
- **Para saber qué restricción ha saltado hay que mirar el SQLSTATE, no el nombre de la
  clase**, y además hay que llegar a él: el encadenado es `sqlalchemy.exc.IntegrityError`
  → `.orig` (wrapper de asyncpg) → `.orig.__cause__` (el error real). Con
  `type(exc.orig).__name__` sale `IntegrityError` y parece que no se ha comprobado nada.

---

## Los guards que protegen esto

Hay dos capas, y la diferencia entre ellas es la lección de este fichero.

**Capa 1 · de ficheros**, en `tests/unit/test_migrations.py`. Cruza los `__tablename__`
de `src/models/` con los `CREATE TABLE` de `migrations/`.

| Guard | Qué protege |
|---|---|
| `test_toda_tabla_del_orm_tiene_migracion` | Que ninguna tabla nueva quede fuera del esquema |
| `test_la_lista_de_tablas_sin_migracion_no_miente` | Que la lista no nombre tablas ya migradas |
| `test_la_lista_de_tablas_sin_migracion_no_nombra_tablas_inventadas` | Que la lista no nombre tablas que ya no están en los modelos |
| `test_migraciones_crean_tablas` (PostgreSQL) | Que las migraciones aplicadas creasen lo que dicen |
| `test_las_migraciones_son_idempotentes_tras_aplicadas` | Que reaplicarlas no rompa nada |

**Capa 2 · contra la base de verdad**, en `tests/integration/test_esquema_completo.py`.
Aplica las migraciones y luego compara **tabla por tabla y columna por columna** lo que
hay con lo que declaran los modelos. Es la que habría parado SPEC-013.

| Guard | Qué protege |
|---|---|
| `test_el_esquema_no_se_aparta_de_los_modelos` | Ninguna diferencia real fuera de la deuda declarada |
| `test_la_deuda_de_tablas_sigue_siendo_deuda` | Que la lista no nombre tablas que ya están bien |
| `test_la_deuda_de_columnas_sigue_siendo_deuda` | Lo mismo para las columnas inconsistentes |
| `test_la_comparacion_esta_contando_algo` | Que el comparador se esté mirando la base de verdad |

**Por qué la capa 2 hace falta y la 1 no basta**: la 1 lee el **código**, y el código
declara lo que el código sabe. Un modelo sin migración no aparece en el inventario de
migraciones, así que no hay nada que faltar. La 2 pregunta a PostgreSQL, y PostgreSQL
contesta.

**Límite conocido de la capa 2**: mira existencia de tabla y columna, tipo, nulabilidad
y valor por defecto. **No** mira claves foráneas, índices, unicidades parciales, enums ni
triggers. Hay guards sueltos para parte de eso, pero no hay uno que compare FKs e índices
entre modelo y esquema. Está escrito en el `docstring` del fichero para que nadie lo lea
como una garantía que no da.

**Límite conocido de la 1**: el fixture de PostgreSQL aplica las migraciones sobre la base
real **sin borrar el esquema**, así que con un fichero de migración borrado de disco,
`test_migraciones_crean_tablas` no falla: las tablas siguen ahí de la ejecución anterior.
Solo fallan las de fichero. Por eso la capa 1 mira el **código**.

### Los guards se han visto fallar

Las mutaciones se aplicaron una a una al `esquema.py` y a `esquema_deuda.py`, y se
comprobó que los tests pasan. La de referencia es la primera:

| Defecto reintroducido | Qué falla |
|---|---|
| Quitar una tabla de la deuda sin migrarla (**el defecto de SPEC-013**) | 3 tests, incluido `test_el_esquema_no_se_aparta_de_los_modelos` |
| La deuda nombra una tabla que ya sí está migrada | `test_la_deuda_de_tablas_sigue_siendo_deuda` |
| `comparar()` deja de notar tablas ausentes | `test_la_deuda_de_tablas_sigue_siendo_deuda` |
| `describir_base()` devuelve siempre vacío | los 4 guards |
| El tipo del modelo se lee sin dialecto PostgreSQL | `test_el_esquema_no_se_aparta_de_los_modelos` |

Un guard que no se ha visto fallar no es un guard, es un comentario.

> **Una trampa del propio experimento**: la primera versión de las mutaciones usaba
> `str.replace()` y tres de siete no se aplicaron porque la indentación no casaba. Los
> tests pasaron y el experimento informó de «el guard no vigila», cuando en realidad
> quería decir «no se tocó nada». Se cambió a `re.subn` **comprobando que hay
> sustituciones**, que es lo único que distingue un «no falla» real de un «no se ha
> ejecutado».

---

## Lo que queda abierto, y no es de esquema

Las 27 tablas están migradas y el esquema coincide con el ORM. Lo que sigue son tres
cosas que **no se pueden arreglar con una migración**, porque son decisiones de diseño
que ya están escritas en el código y que alguien tiene que querer cambiar:

1. **`configuracion_sii` duplica `config_sii`.** SPEC-012 y SPEC-029 tienen cada una su
   configuración del SII, y las dos se leen desde distinto código. Ahora las dos tablas
   existen. Cuál se queda, o si se fusionan, es una decisión de producto.
2. **51 referencias sueltas sin FK**, en 51 columnas de todo el ORM (22 de ellas en las 27
   que se han migrado). Decisión tomada el 2026-09-29 y documentada; cerrarlas es un
   trabajo con su propio análisis, no un apéndice.
3. **`evento_auditoria_acceso.rol_id` → `roles.id`** es una FK de una sola columna a una
   tabla que sí tiene `empresa_id`, o sea que no la mira. Corregirla exige cambiar el
   modelo y una migración nueva sobre `007_rbac.sql`, que ya está aplicada.

Y dos cosas que son deuda de la **herramienta**, no del esquema:

- **No hay Alembic.** El runner es propio: 32 ficheros `.sql` re-aplicados en cada
  ejecución, e idempotencia como requisito, no como propiedad. Ver la sección 50 de
  `AGENTS.md` para lo que le falta frente a Alembic y por qué instalarlo no es el
  siguiente paso.
- **El fixture `pg_engine` aplica las migraciones sobre la base de verdad sin borrarla.**
  Con un fichero de migración borrado de disco, sus tests no fallan: las tablas siguen
  ahí de la ejecución anterior. Por eso los guards de esquema miran el **código** y
  escriben en su propia tabla de deuda, en vez de fiarse del estado de la base.

---

## Cómo confirmar una reparación

```powershell
# 1. Aplicar (idempotente: la segunda vez no hace nada)
cd backend
$env:PYTHONPATH="src"; ..\.venv\Scripts\python.exe -m db.migrate

# 2. La capa 1
..\.venv\Scripts\python.exe -m pytest tests/unit/test_migrations.py -q

# 3. La capa 2, contra PostgreSQL de verdad
$env:TEST_DATABASE_URL="postgresql+asyncpg://...@localhost:5432/contabilidad"
..\.venv\Scripts\python.exe -m pytest tests/integration/test_esquema_completo.py -q

# 4. Comprobar un endpoint que antes daba 500
#    (con backend y frontend levantados)
```

Cuando las 27 estén migradas, `TABLAS_SIN_MIGRACION` pasa a `set()` y este fichero queda
obsoleto. Lo dice así el propio guard: la lista solo puede encogerse.
