# Quickstart: Validación de Navegación y superficies (SPEC-031)

**Fecha**: 2026-09-27 | **Plan**: [plan.md](plan.md) | **Spec**: [spec.md](spec.md)

Guía de validación manual de los seis recorridos. Cada recorrido dice **qué hacer**, **qué se
espera** y **qué requisito comprueba**. No incluye código de implementación: eso vive en
`tasks.md`.

---

## Prerrequisitos

```powershell
# Backend con el esquema migrado (incluye 022_favoritos.sql)
cd backend
$env:PYTHONPATH="src"
..\.venv\Scripts\python.exe -m db.migrate

# Servidor
$env:PYTHONPATH="src"; ..\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

```powershell
# Frontend
cd frontend
npm install
$env:NEXT_TELEMETRY_DISABLED="1"
node node_modules/next/dist/bin/next dev
```

Datos mínimos para los recorridos: **dos empresas** (A y B) con PGC sembrado, **una con
ejercicio anterior abierto y el actual abierto** (el caso 31 de diciembre), y un usuario con
los tres roles disponibles para probar el filtrado de permisos.

> El recorrido R6 necesita que el usuario tenga al menos dos años con asientos. Si el conjunto
> de datos no lo tiene, hay que crear 5 asientos en 2025 y 3 en 2026 antes de empezar.

---

## R1 · Identidad antes que nada (FR-001, FR-002)

**Qué hacer**: iniciar sesión, pulsar el nombre de usuario de la zona de contexto y elegir
**Cerrar sesión**. Después escribir `/asientos/diario` en la barra de direcciones y pulsar
Enter.

**Se espera**: el menú se cierra y aparece la pantalla de identificación; después,
redirección inmediata a `/login` **sin pintar** la estructura de la página. Ningún
rail, ningún selector, ningún dato.

Repetir con `/asientos`, `/vencimientos` y `/contabilidad`: las cuatro redirigen.

**Comprueba**: FR-001, FR-002, FR-032.

> **Añadido 2026-09-29**: esta redacción decía «cerrar sesión» sin decir cómo, porque
> **cerrar sesión no existía en ninguna parte de la aplicación**: el nombre de usuario
> era un `<span>` de texto, y para salir había que vaciar el `localStorage` a mano. El
> recorrido era imposible de reproducir tal como estaba escrito, y esa es una forma
> de que un recorrido de quickstart describa un hueco en vez de una funcionalidad.

---

## R2 · La zona de contexto (FR-002, FR-016, FR-017)

**Qué hacer**: iniciar sesión como un usuario con acceso a la empresa A y a la B.

**Se espera**: en la zona superior, antes de cualquier contenido, se ven las tres cosas: nombre
de usuario, empresa activa y ejercicio activo. El desplegable de ejercicio muestra cada año
con su **número de asientos** y un estado distinguible.

Con el ejercicio anterior abierto, ese año aparece con tono ámbar y la etiqueta `cerrando`. El
año cerrado aparece con tono rojo, la etiqueta `cerrado` y **no** es seleccionable.

Comprobar que el estado **no depende solo del color**: con el color desactivado se sigue
leyendo la etiqueta de texto.

Pulsar el nombre de usuario: se abre el **menú de sesión**, con la identidad completa arriba y
tres acciones debajo — **Cambiar de empresa**, **Cambiar de ejercicio** y **Cerrar
sesión**.

- Abrir **Cambiar de empresa**: aparece la lista con la razón social y el NIF de cada
  empresa, y la activa marcada. Elegir otra cambia empresa y ejercicio a la vez.
- Abrir **Cambiar de ejercicio**: aparece la lista con año, etiqueta de estado y
  `n asientos`. Los cerrados salen deshabilitados con el motivo.
- Con una sola empresa, el apartado lo dice en lugar de abrir una lista de un elemento.

En dispositivo pequeño, la hoja de contexto lleva el mismo menú.

**Comprueba**: FR-002, FR-003, FR-016, FR-017, FR-032, y D7 (estado por color solo está
prohibido).

---

## R3 · Los seis destinos (FR-008, FR-009, FR-012)

**Qué hacer**: en escritorio, recorrer el rail de arriba abajo.

**Se espera**: 6 destinos, siempre en el mismo orden, sin desplazamiento, con **un** único
indicador de destino activo. Ninguna etiqueta aparece recortada.

Entrar en cada uno. Cada superficie muestra su listado de destinos y un resumen con datos del
ejercicio activo.

**Comprueba**: FR-008, FR-009, FR-010, FR-012.

---

## R4 · Facturar en dos ejercicios (FR-004, FR-005, FR-007, FR-018, FR-019)

**Qué hacer**: con 2025 y 2026 ambos abiertos:

1. Seleccionar 2025. Registrar un asiento. Anotar su número.
2. Seleccionar 2026. Registrar otro asiento.
3. Abrir el diario de cada ejercicio.

**Se espera**: el asiento del paso 1 está en 2025 y el del paso 2 en 2026, **coincida con lo
que el selector mostraba en cada momento**.

4. Intentar registrar un asiento con 2025 seleccionado, y en otra pestaña seleccionar 2026 y
   registrar: cada escritura va a su ejercicio.
5. Cambiar a la empresa B manteniendo 2025 seleccionado.

**Se espera**: la empresa B recalcula su contexto y **no** arrastra el ejercicio de la A si no
le pertenece; si 2025 no existe en B, la aplicación avisa y elige el ejercicio válido de B.

6. Abrir una pantalla que lleve `?ejercicio=2025` con la cabecera en 2026.

**Se espera**: gana el parámetro explícito (2025), no la cabecera.

7. Con un ejercicio cerrado seleccionado, intentar escribir.

**Se espera**: rechazo con un mensaje que explique que el ejercicio está cerrado, no un error
técnico.

**Comprueba**: FR-004, FR-005, FR-007, FR-018, FR-019, y D4 (el estado mostrado y la
posibilidad de escribir nunca discrepan).

---

## R5 · Favoritos por usuario y por empresa (FR-021 a FR-027)

**Qué hacer**: marcar 3 destinos como favoritos: `vencimientos`, `conciliacion`, `asientos`.

**Se espera**: aparecen en su propia sección en el panel, **por encima** del listado de la
superficie, y el rail **no cambia de orden ni de contenido**.

1. Cerrar sesión y volver a entrar.

**Se espera**: los 3 favoritos siguen ahí, en el mismo orden.

2. Marcar un sexto favorito.

**Se espera**: se rechaza con el límite de 5 y **no se borra** ninguno de los anteriores.

3. Iniciar sesión con otro usuario de la misma empresa.

**Se espera**: **no** ve los favoritos del usuario anterior. Son por usuario.

4. Cambiar a la empresa B y volver a la A.

**Se espera**: cada empresa muestra su propio conjunto. Un usuario que marque algo distinto en
B no lo ve en A.

5. Cambiar de rol al usuario para que pierda el permiso de uno de sus favoritos.

**Se espera**: ese favorito **desaparece de la vista pero no se borra**. Al recuperar el
permiso, **reaparece**.

**Comprueba**: FR-021, FR-022, FR-023, FR-024, FR-025, FR-027, y D5 (la FK compuesta impide
que un favorito exista sin vinculación del usuario a la empresa).

---

## R6 · La pantalla de cada superficie (FR-010, FR-028)

**Qué hacer**: entrar en las 5 landings nuevas.

**Se espera**: cada una lista sus destinos y un resumen con datos del ejercicio activo. Cambiar
de ejercicio y volver a entrar: el resumen refleja el ejercicio nuevo.

En **Maestros**, el listado de empresas muestra solo las empresas del ámbito del usuario, con su
detalle y el acceso al alta.

**Comprueba**: FR-010, FR-028, y el criterio de que ninguna superficie queda sin resumen.

---

## R7 · Rutas que cambian de sitio (FR-014, FR-026)

**Qué hacer**: abrir cada dirección antigua.

| Dirección antigua | Se espera |
|---|---|
| `/contabilidad/asientos/nuevo` | aparece el formulario de nuevo asiento |
| `/contabilidad/import-export` | aparece la pantalla de import/export |
| `/cierre` | aparece el listado de cierres |
| `/cobros` | aparece el listado de cobros y pagos |
| `/tesoreria/efe` | aparece el estado de flujos de efectivo |

**Se espera**: la canónica, sin montar la pantalla intermedia, y la URL queda en la
canónica.

Luego: con un favorito en `asientos`, comprobar que sigue llegando a la pantalla correcta.

**Comprueba**: FR-014, FR-026, y la historia 6.

---

## R8 · Móvil (FR-003, FR-011)

**Qué hacer**: la misma aplicación en una ventana de menos de 600dp de ancho.

**Se espera**:

- Barra inferior con 4 destinos y «Más», **no** un rail.
- El chip de contexto lleva **empresa y ejercicio juntos**, y al pulsarlo se abre una hoja con
  los dos selectores.
- Cambiar de empresa o de ejercicio y volver a la pantalla en curso: se hace en 3 acciones.
- Los favoritos están en el mismo lugar que en escritorio.
- La hoja de contexto es operable con teclado.

**Comprueba**: FR-003, FR-011, y D1 (en compacto, barra de navegación y no rail, según M3).

---

## R9 · Teclado (research D7, CHK029, CHK031)

**Qué hacer**: recorrer toda la aplicación **sin ratón**, con `Tab`, `Enter` y las flechas.

**Se espera**:

1. El orden de tabulación es: zona de contexto → rail → panel → contenido.
2. El foco es **visible** en todos los elementos, incluidos los destinos con estado ámbar y rojo.
3. `Enter` en un destino navega. Las flechas se mueven dentro del panel cuando tiene foco.
4. La pantalla de entrada contable conserva sus atajos de teclado: la navegación nueva **no** se
   los ha quitado.
5. Los cuatro estados de ejercicio se distinguen **leyendo la etiqueta**, no solo por el color.

**Comprueba**: D7, y la constitution «Normas del Frontend · usabilidad por teclado».

---

## R10 · Permisos y pérdida de rol (caso borde de la historia 2)

**Qué hacer**: con un usuario `READ_ONLY`, entrar a la aplicación. Después, con un
`ACCOUNTANT` al que se le revoca un módulo entero en la matriz.

**Se espera**:

- El rail solo muestra los destinos que puede abrir. No hay destinos rotos ni iconos que
  lleven a un error.
- La superficie totalmente inaccesible **no deja un hueco vacío** en el rail.
- Perder un permiso no borra los favoritos marcados (ver R5.5).

**Comprueba**: caso borde de la historia 2, FR-024, y D6.

---

## Puertas de la suite

El quickstart cubre lo que **la suite no puede ver**. Las puertas automáticas son:

```powershell
# Backend
..\.venv\Scripts\python.exe -m pytest tests/unit/test_contexto_ejercicio.py `
    tests/unit/test_favoritos_servicio.py `
    tests/unit/test_guard_mapa_superficies.py -q
..\.venv\Scripts\python.exe -m pytest tests/integration/test_contexto_tenant_isolation.py `
    tests/integration/test_navegacion_contratos.py -q
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m ruff check src tests
..\.venv\Scripts\python.exe -m mypy -p api -p models -p services -p database -p base -p db -p main -p config
```

```powershell
# Frontend
node node_modules/typescript/bin/tsc --noEmit
node node_modules/eslint/bin/eslint.js src
$env:NEXT_TELEMETRY_DISABLED="1"; node node_modules/next/dist/bin/next build
```

**Las cuatro comprobaciones que la suite DEBE incluir**, porque son las que la constitution
exige para esta feature:

| Comprobación | Dónde |
|---|---|
| Un ejercicio de la empresa B no se resuelve en el contexto de la A | `test_contexto_tenant_isolation.py` |
| `n_asientos` de la A no incluye asientos de la B con el mismo ejercicio | mismo fichero |
| Marcar y desmarcar favoritos escriben en `audit_log` en la misma transacción | `test_favoritos_servicio.py` |
| Ninguna pantalla queda fuera del mapa de superficies | `test_guard_mapa_superficies.py` |

Y una comprobación transversal que ya existe y **no debe romperse**:
`api.routes_registry.rutas_sin_permiso` sigue en **0**.

---

## Fuera de alcance de esta validación

- Gestión de altas de usuario, cambio obligatorio de contraseña y registro de quién hace cada
  apunte: **SPEC-032**.
- Pruebas de seguridad del guard de sesión. El `middleware.ts` comprueba presencia de cookie y
  redirige; la frontera real es el 401 del backend, que ya funciona (research D2).
- Cualquier validación de la partida doble: esta feature no genera asientos. La verificación
  es la suite completa, que incluye el trigger de balance diferido.

---

## Qué de esto está automatizado

Los diez recorridos son **manuales**: describen lo que hay que mirar en un navegador, y
un test no puede mirar un rail. Lo que sí se puede comprobar sin una persona delante de
la pantalla se comprueba en
`backend/tests/integration/test_quickstart_navegacion.py`, y ese fichero enumera en
`MANUAL` lo que queda para revisión visual, con el requisito que cubre cada punto.

Reparto:

| Recorrido | Automatizado | Qué queda a ojo |
|---|---|---|
| R1, R2 | El orden de montaje, y que empresa, ejercicio e identidad se pinten | Que la identidad se lea antes que cualquier dato de negocio |
| R3 | Las seis superficies, su orden fijo, y que cada una tenga landing | Que el indicador activo sea único y que no se recorte ninguna etiqueta |
| R4 | Nada: es escritura real sobre dos ejercicios | El recorrido entero |
| R5 | Los favoritos por usuario, por empresa, y el límite de 5 (suite de US4) | Marcar, cambiar de empresa y de usuario, y ver que reaparece |
| R6 | Que las siete pantallas nuevas existan | Que cada una muestre su lista de destinos sin huecos |
| R7 | Que el redirect declarado apunte a un canónico que existe | Abrir la ruta antigua en el navegador |
| R8 | Que el rail se oculte en compacto y exista la barra inferior | La hoja de contexto en móvil y el «Más» |
| R9 | Que los destinos se pinten con enlaces reales | Recorrer el shell entero con teclado |
| R10 | El efecto en la API (403 y `accesible: false`) | Quitar un permiso en la matriz y mirar la pantalla |

**Lo que no se ha automatizado y hay que mirar a mano**: el recorrido R4 entero, porque
crea asientos, y la mitad visual de todos los demás. La suite de tests no sustituye a esa
revisión, y dar por validado R1-R10 solo con tests sería falso.

---

## Enmienda 2026-09-28 · por qué R3 y R6 no se habían automatizado de verdad

Al abrir la aplicación después del cierre, las seis landings estaban vacías: se veían los
títulos de las secciones y no se podía entrar en ningún proceso. El rail se veía
perfecto, y ninguna de las cuatro puertas de la spec lo detectó.

La tabla de arriba dice, para **R3**, que lo automatizado es «las seis superficies, su
orden fijo, y que cada una tenga landing». Eso era lo que se comprobaba: que el mapa
**declarara** seis superficies y que cada una declarara una landing. Lo que **no** se
comprobaba es que la aplicación supiera *abrir* esa landing, y no la sabía:
`superficieDeRuta()` buscaba la ruta entre los destinos de cada superficie y nunca entre
su landing, así que las seis devolvían «no hay superficie» y el panel no pintaba ni la
rejilla de destinos ni el resumen. La misma línea de la tabla de arriba, para **R6**,
decía «que cada una muestre su lista de destinos sin huecos», y se comprobaba que las
siete pantallas existieran en disco.

La lección es sobre la palabra «automatizado» en esa tabla, y conviene tenerla presente al
leer cualquier fila: **una prueba de que algo está declarado no es una prueba de que
funciona**. Aquí las dos cosas se confundieron porque ambas se escriben mirando el mismo
fichero, `surfaces.ts`, y una regex no distingue «el mapa dice 6 superficies» de «la
aplicación resuelve 6 superficies».

### Qué se ha automatizado desde entonces

`backend/tests/integration/test_navegacion_resolucion.py` compila `surfaces.ts` con el
`tsc` del propio proyecto y lo evalúa con `node`, de modo que la prueba **ejecuta** el
resolutor en vez de leer su declaración. Con ello, la mitad decicional de R3 y R6 —qué
ruta pertenece a qué superficie, y a dónde lleva cada enlace— pasa a ser verificable, y
era justo la mitad que estaba rota.

Lo que **sigue** sin automatizarse, y hay que mirar por la misma razón que antes:

| Recorrido | Lo que ahora se comprueba | Lo que sigue siendo a ojo |
|---|---|---|
| **R3** | Que la landing de cada superficie resuelve a esa superficie, con barra final y con query; que cada destino resuelve a la que lo declara; que ninguna ruta se declara en dos superficies | Que la rejilla se **pinte**, que el indicador activo sea único y que no se recorte ninguna etiqueta |
| **R6** | Que los «ir a» del resumen apuntan a una pantalla que existe **y** a una superficie; que el ancla de cada ajuste existe en su página | Que el resumen muestre cifras, y que los enlaces funcionen al pulsarlos |

La comprobación de R3 y R6 más honesta que hay ahora es la de siempre y sigue siendo
manual: **abrir `/contabilidad` y mirar**. Lo que ha cambiado es que, si la navegación
vuelve a romperse, la suite lo dirá antes de que haya que abrirla.
