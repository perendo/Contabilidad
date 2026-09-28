# Navigation Contract: Navegación y superficies (SPEC-031)

**Fecha**: 2026-09-27 | **Plan**: [plan.md](plan.md) | **Research**: [research.md](research.md)

Contrato de la capa de navegación del cliente. Es la parte de la feature que **no** se puede
comprobar con la suite del backend, así que necesita su propia especificación y su propio
guard.

---

## 1. Las seis superficies (orden fijo)

El orden es estable e independiente del uso (FR-009). M3: «Always put the rail in the same
place» y «Don't use the active indicator for more than one navigation item at a time».

| # | Clave | Etiqueta | Landing | Ámbito |
|---|---|---|---|---|
| 1 | `contabilidad` | Contabilidad | `/contabilidad` | plan de cuentas, catálogo, asientos, plantillas, documentos, inmovilizado, divisas, import/export, ejercicio y cierre |
| 2 | `facturacion` | Facturación | `/facturacion` | facturas, series |
| 3 | `tesoreria` | Tesorería | `/tesoreria` | operación, instrumentos, banco, previsión |
| 4 | `informes` | Informes | `/informes` | balance, PyG, mayor, sumas, coste, presupuestos, cuentas anuales, flujos de efectivo |
| 5 | `fiscal` | Fiscal | `/fiscal` | IVA, modelos, retenciones, impuesto sobre sociedades, ONG |
| 6 | `maestros` | Maestros | `/maestros` | terceros, centros, condiciones, empresas, permisos, exportación, ajustes |

`/tesoreria` ya existe como panel de tesorería (SPEC-021) y **se reutiliza** como landing: no
se crea una octava página. Las otras cinco son nuevas.

---

## 2. Membresía completa de cada superficie

Este es el requisito que CHK001 exige que sea explícito, para que FR-012 sea verificable.
Toda pantalla existente aparece exactamente una vez.

### 1 · Contabilidad

| Destino (clave) | Etiqueta | Ruta | Grupo |
|---|---|---|---|
| `plan-cuentas` | Plan de cuentas | `/cuentas` | Configuración |
| `plan-cuentas-nueva` | Nueva cuenta | `/cuentas/nueva` | *acción* |
| `catalogo` | Catálogo de cuentas | `/catalogo` | Configuración |
| `catalogo-detalle` | Detalle de catálogo | `/catalogo/[id]` | *hijo* |
| `catalogo-importar` | Importar catálogo | `/catalogo/importar` | *acción* |
| `catalogo-reclasificar` | Reclasificar saldos | `/catalogo/reclasificar` | *acción* |
| `asientos` | Asientos | `/asientos/diario` | Registro |
| `asientos-nuevo` | Nuevo asiento | `/asientos/nuevo` | *acción* |
| `asientos-detalle` | Detalle de asiento | `/asientos/[id]` | *hijo* |
| `plantillas` | Plantillas | `/plantillas` | Registro |
| `plantillas-nueva` | Nueva plantilla | `/plantillas/nueva` | *acción* |
| `plantillas-detalle` | Detalle de plantilla | `/plantillas/[id]` | *hijo* |
| `plantillas-generar` | Generar asiento | `/plantillas/[id]/generar` | *acción* |
| `documentos` | Documentos | `/documentos` | Registro |
| `inmovilizado` | Inmovilizado | `/inmovilizado` | Activos |
| `inmovilizado-alta` | Alta de activo | `/inmovilizado/alta` | *acción* |
| `inmovilizado-detalle` | Detalle de activo | `/inmovilizado/[id]` | *hijo* |
| `inmovilizado-amortizaciones` | Amortizaciones | `/inmovilizado/amortizaciones` | Activos |
| `divisas` | Divisas | `/divisas` | Configuración |
| `divisas-tipos` | Tipos de cambio | `/divisas/tipos` | *hijo* |
| `divisas-historial` | Historial de tipos | `/divisas/tipos/historial` | *hijo* |
| `divisas-valoracion` | Valoraciones | `/divisas/valoracion` | *hijo* |
| `divisas-asiento` | Asiento en divisa | `/divisas/asientos/nuevo` | *acción* |
| `import-export` | Importar y exportar | `/asientos/import-export` | Registro |
| `ejercicio` | Ejercicio y cierre | `/cierres` | Ciclo |
| `apertura` | Apertura | `/apertura` | Ciclo |
| `cierre-intermedio` | Cierre intermedio | `/cierres/intermedio` | Ciclo |
| `cierre-anual` | Cierre anual | `/cierres/anual` | Ciclo |
| `reaperturas` | Reaperturas | `/cierres/reaperturas` | Ciclo |
| `cierres-detalle` | Detalle de cierre | `/cierres/[id]` | *hijo* |

### 2 · Facturación

| Destino | Etiqueta | Ruta |
|---|---|---|
| `facturas` | Facturas | `/facturacion/facturas` |
| `facturas-nueva` | Nueva factura | `/facturacion/facturas/nueva` *(acción)* |
| `facturas-detalle` | Detalle de factura | `/facturacion/facturas/[id]` *(hijo)* |
| `facturas-rectificar` | Rectificar factura | `/facturacion/facturas/[id]/rectificar` *(acción)* |
| `series` | Series | `/facturacion/series` |

### 3 · Tesorería (4 grupos, M3 progressive disclosure)

| Destino | Etiqueta | Ruta | Grupo |
|---|---|---|---|
| `vencimientos` | Cobros y pagos | `/vencimientos` | Operación |
| `antiguedad` | Antigüedad de saldos | `/antiguedad` | Operación |
| `medios-pago` | Medios de pago | `/tesoreria/cobros` | Operación |
| `remesas` | Remesas | `/remesas` | Operación |
| `remesas-nueva` | Nueva remesa | `/remesas/nueva` | *acción* |
| `remesas-detalle` | Detalle de remesa | `/remesas/[id]` | *hijo* |
| `devoluciones` | Devoluciones | `/devoluciones` | Operación |
| `devoluciones-detalle` | Detalle de devolución | `/devoluciones/[id]` | *hijo* |
| `efectos` | Efectos | `/efectos` | Instrumentos |
| `efectos-nuevo` | Nuevo efecto | `/efectos/nuevo` | *acción* |
| `efectos-detalle` | Detalle de efecto | `/efectos/[id]` | *hijo* |
| `anticipos` | Anticipos | `/anticipos` | Instrumentos |
| `anticipos-nuevo` | Nuevo anticipo | `/anticipos/nuevo` | *acción* |
| `anticipos-detalle` | Detalle de anticipo | `/anticipos/[id]` | *hijo* |
| `cesiones` | Cesión de cobros | `/cesiones` | Instrumentos |
| `cesiones-nueva` | Nueva cesión | `/cesiones/nueva` | *acción* |
| `cesiones-detalle` | Detalle de cesión | `/cesiones/[id]` | *hijo* |
| `conciliacion` | Conciliación | `/conciliacion` | Banco |
| `conciliacion-importar` | Importar extracto | `/conciliacion/importar` | *acción* |
| `conciliacion-detalle` | Detalle de conciliación | `/conciliacion/[id]` | *hijo* |
| `conciliacion-periodos` | Periodos conciliados | `/conciliacion/periodos` | Banco |
| `previsiones` | Previsión de tesorería | `/tesoreria/previsiones` | Previsión |
| `previsiones-detalle` | Detalle de previsión | `/tesoreria/previsiones/[id]` | *hijo* |
| `alertas-liquidez` | Alertas de liquidez | `/tesoreria/alertas` | Previsión |

### 4 · Informes

| Destino | Etiqueta | Ruta |
|---|---|---|
| `balance` | Balance | `/balance` |
| `pyg` | Pérdidas y ganancias | `/pyg` |
| `mayor` | Libro mayor | `/informes/mayor` |
| `sumas-saldos` | Sumas y saldos | `/informes/sumas-saldos` |
| `coste` | Informe de costes | `/informes/costes` |
| `presupuestos` | Presupuestos | `/presupuestos` |
| `presupuestos-seguimiento` | Seguimiento | `/presupuestos/seguimiento` |
| `presupuestos-informes` | Informes de desviación | `/presupuestos/informes` |
| `cuentas-anuales` | Cuentas anuales | `/cuentas-anuales` |
| `flujos-efectivo` | Flujos de efectivo | `/efe` |

### 5 · Fiscal

| Destino | Etiqueta | Ruta |
|---|---|---|
| `libros-iva` | Libros de IVA | `/libros-iva` |
| `modelos` | Modelos fiscales | `/modelos` |
| `retenciones` | Retenciones | `/fiscal/retenciones` |
| `retenciones-nueva` | Nueva liquidación | `/fiscal/retenciones/nueva` *(acción)* |
| `retenciones-detalle` | Detalle de retención | `/fiscal/retenciones/[id]` *(hijo)* |
| `modelo-190` | Modelo 190 | `/fiscal/modelos/190` |
| `impuesto-sociedades` | Impuesto sobre Sociedades | `/fiscal/impuesto-sociedades` |
| `is-nueva` | Nuevo cálculo | `/fiscal/impuesto-sociedades/nuevo` *(acción)* |
| `is-detalle` | Detalle del cálculo | `/fiscal/impuesto-sociedades/[id]` *(hijo)* |
| `modelo-200` | Modelo 200 | `/fiscal/modelo-200` |
| `ong-subvenciones` | Subvenciones | `/ong/subvenciones` |
| `ong-subvenciones-detalle` | Detalle de subvención | `/ong/subvenciones/[id]` *(hijo)* |
| `ong-libros` | Libros oficiales | `/ong/libros` |
| `ong-caja` | Caja | `/ong/caja` |
| `ong-caja-detalle` | Detalle de caja | `/ong/caja/[id]` *(hijo)* |

### 6 · Maestros

| Destino | Etiqueta | Ruta |
|---|---|---|
| `terceros` | Terceros | `/terceros` |
| `terceros-nuevo` | Nuevo tercero | `/terceros/nuevo` *(acción)* |
| `terceros-detalle` | Detalle de tercero | `/terceros/[id]` *(hijo)* |
| `condiciones-pago` | Condiciones de pronto pago | `/terceros/condiciones` |
| `centros-coste` | Centros de coste | `/centros` |
| `centros-nuevo` | Nuevo centro | `/centros/nuevo` *(acción)* |
| `empresas` | Empresas | `/maestros/empresas` *(nueva)* |
| `empresas-nueva` | Alta de empresa | `/empresas/nueva` *(acción)* |
| `permisos` | Permisos y roles | `/permisos` |
| `permisos-auditoria` | Auditoría de accesos | `/permisos/auditoria` |
| `exportaciones` | Exportación integral | `/exportaciones` |
| `exportaciones-nueva` | Nueva exportación | `/exportaciones/nueva` *(acción)* |
| `exportaciones-detalle` | Detalle de exportación | `/exportaciones/[id]` *(hijo)* |
| `ajustes-sii` | Ajustes de información fiscal | *(ajuste en el panel: `/maestros#ajustes-sii`)* |

> **Enmienda 2026-09-28**: la fila de arriba decía «ajuste en el panel, no ruta propia» y
> no decía **dónde** estaba. El panel la renderizaba como `<Link href="">`, que resuelve a
> la URL actual: un enlace que no lleva a ninguna parte, con la misma pinta que los de
> verdad. El ajuste **no tiene ruta** (sigue siendo una sección, no una pantalla), pero
> tiene **ancla**, y el ancla se declara en el mapa como `Destino.ancla`, no en el
> componente. El panel compone `{landing}#{ancla}` mediante `enlaceDeDestino()`, que
> devuelve `null` —nunca `""`— cuando no hay destino navegable, de modo que una entrada
> sin ruta no pueda salir como enlace. Ver la sección 7.

**Recuento**: 103 pantallas. Las 5 páginas de landing nuevas y `/maestros/empresas` suman
pantallas nuevas; las 5 rutas antiguas se convierten en redirect y dejan de contar como
pantalla; `/` (raíz) se sustituye por la landing de Contabilidad.

> **Comprobado por script, no a ojo**: al contrastar el mapa con las 103 pantallas reales
> (`page.tsx`), la primera pasada dejaron sin ubicar `/` y `/antiguedad`. La segunda, con las
> dos ya asignadas, da cobertura completa. Las pantallas que el mapa cita y que aún no existen
> son exactamente las 6 previstas: 5 landings más `/maestros/empresas`. Un mapa de 103
> elementos escrito a mano sin contraste previo contiene huecos; por eso el guard de §6 es
> obligatorio y no opcional.

---

## 2bis · La landing es resoluble (enmienda 2026-09-28)

Este requisito **no estaba en el contrato** y su ausencia es la causa de que la
aplicación se abriera vacía.

La **landing de una superficie es su puerta de entrada**: es a donde apunta el rail, es la
primera pantalla que ve el usuario de cada superficie, y es la única que monta el resumen.
Por tanto la función que resuelve «qué superficie corresponde a esta ruta»
(`superficieDeRuta`) tiene que considerar la landing **además** de los destinos.

Si solo considera los destinos, y ninguna superficie declara su propia landing como
destino, las seis landings devuelven `undefined`. Y `undefined` en el panel significa tres
cosas a la vez, todas rotten:

| Consecuencia | Efecto visible |
|---|---|
| `grupos` queda vacío | la rejilla de destinos no se pinta: los 57 enlaces reales son inalcanzables desde su propia página de entrada |
| `esLanding` es `false` | `ResumenSuperficie` no se monta: `GET /api/v1/resumenes/{superficie}` no se llama nunca |
| el aviso de «no pertenece a ninguna superficie» | se pinta en las seis landings, siempre, sin ser verdad |

El contrato que se añade: **toda ruta que una superficie declara, incluida su `landing`,
resuelve a esa superficie**. Y su contraparte, que también hay que escribir: **ninguna ruta
se declara en dos superficies**, porque añadir la landing a la búsqueda crea la posibilidad
de solape.

---

## 3. Reglas de navegación

| Regla | Origen | Aplicación |
|---|---|---|
| El rail tiene 6 destinos, siempre en el mismo orden | FR-009, M3 rail 3-7 | Fijo, no se reordena por uso |
| Solo un destino activo | M3 | Indicador único y exclusivo |
| Las acciones no son destinos | FR-013, M3 «destinations are places» | Las marcadas `accion` salen del panel |
| Los favoritos no alteran el rail | FR-023 | Sección propia encima del panel, máx. 5 |
| Rail fijo, panel contextual | M3 rail expandido | El panel NO es un drawer (desaconsejado en M3 Expressive) |
| Móvil: barra inferior, no rail | M3 «don't use a rail on compact» | 4 destinos + «Más» |
| El perfil va en la barra superior | M3 / SAP | Zona de contexto, no el rail |
| Etiquetas cortas, sin recortar | M3 «don't truncate» | Se acortan, no se truncan |

---

## 4. Rupturas de pantalla (M3)

| Clase | Ancho | Componente |
|---|---|---|
| Compacto | < 600dp | navigation bar (4 + Más) + chip de contexto |
| Medio | 600-839dp | rail colapsado + panel |
| Expandido | 840-1199dp | rail colapsado + panel |
| Grande | 1200-1599dp | rail colapsado + panel |
| Extra-grande | >= 1600dp | rail colapsado + panel |

En compacto, el chip de contexto lleva **empresa y ejercicio juntos** y abre un bottom sheet,
porque es donde más se olvida en cuál de los dos se está (FR-003, FR-011).

---

## 5. Operabilidad por teclado (research D7)

| Aspecto | Regla |
|---|---|
| Orden de tabulación | zona de contexto → rail → panel → contenido |
| Indicador de foco | visible en todo elemento navegable, incluidos los estados ámbar y rojo |
| `Enter` | navega al destino con foco |
| Flechas | se reservan al panel cuando tiene foco; nunca capturadas globalmente |
| Atajos globales de una tecla | **prohibidos** en la navegación; degradarían la entrada contable que la constitution declara obligatoria |
| Estado por color solo | **prohibido**; todo estado lleva etiqueta de texto |

---

## 6. Guard de mapa

`test_guard_mapa_superficies.py` (backend) falla si existe un `page.tsx` fuera del mapa, y
falla si el mapa declara una ruta que no existe. Con 103 pantallas, un mapa manual se
desincroniza en semanas; el guard lo convierte en deuda visible el mismo día. Es el mismo
patrón que `test_guard_siembra_empresa.py` (SPEC-031 research, AGENTS.md §47).

**Excepciones explícitas** (y solo estas): `/login`, `/` (raíz) y los 5 archivos de redirect.
Si la lista crece, la lista envejece y el guard deja de ser una red.

---

## 7. Guard de resolución (enmienda 2026-09-28)

El guard de §6 y el resto de tests de la feature leen `surfaces.ts` con expresiones
regulares. Comprueban que el mapa **declare** lo correcto, no que la aplicación
**resuelva** lo correcto. Las cuatro puertas que la spec acepta como sustituto de un test
de frontend (`tsc`, ESLint, `next build`, pytest) pasan con la navegación rota: un `if`
invertido dentro de una función pura no cambia nada de lo que un regex puede ver.

Falta por tanto una categoría de guard que el proyecto no tenía: uno que **ejecute** el
código. `test_navegacion_resolucion.py` (21 tests) compila `surfaces.ts` con el `tsc` del
propio proyecto y evalúa el mapa con `node`, de modo que la prueba ejercita el resolutor
real.

Reimplementar la lógica en Python **no serviría**: el defecto no estaba en la comparación,
sino en que la función no llegaba a comparar la landing. La copia habría pasado en verde
con la pantalla rota.

Cubre, como mínimo:

| # | Comprobación |
|---|---|
| 1 | La landing de cada superficie resuelve a esa superficie, con barra final y con query |
| 2 | Cada destino del panel resuelve a la superficie que lo declara, y no a otra |
| 3 | Ninguna ruta se declara en dos superficies |
| 4 | Las pantallas de detalle resuelven por su patrón `[id]` |
| 5 | Ninguna entrada del panel produce un enlace vacío, y el panel usa la función que resuelve el enlace |
| 6 | El ancla de cada ajuste existe como `id` en la página donde se monta |
| 7 | Cada «ir a» del resumen apunta a una pantalla real **y** resuelve a una superficie |
| 8 | La forma del mapa no ha cambiado: 6 superficies, rail de 6, grupos, y las claves coinciden con `DESTINOS` del backend |

`node` ya es dependencia dura (`next build` no corre sin él), así que no se añade ninguna.
Si `node` o `tsc` no están, los tests se **omiten con motivo explícito**: es preferible
omitir una comprobación a aparentar que se hizo.

**Regla para la lista de guards**: todo guard se comprueba **reintroduciendo su
defecto**. Un guard que no se ha visto fallar nunca no es un guard, es un comentario.
