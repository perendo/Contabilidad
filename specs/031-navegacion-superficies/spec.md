# Feature Specification: Navegación y superficies

**Feature Branch**: `031-navegacion-superficies`

**Created**: 2026-09-27

**Status**: Draft

**Input**: User description: "SPEC-031 Navegación y superficies. Ordenar todas las opciones disponibles del programa contable según los principios de diseño de Material Design, proponiendo una estructura por superficies. Añadir un rail de 6 destinos precedido por la identificación del usuario y por los selectores de empresa y ejercicio, con cambio de empresa y ejercicio también en móvil (al cierre del ejercicio se contabiliza en dos ejercicios a la vez). Crear páginas de inicio con resumen para cada superficie, una lista de empresas en Maestros y un sistema de favoritos por usuario, que varían según el puesto."

## User Scenarios & Testing *(mandatory)*

<!--
  IMPORTANTE: las historias son journeys priorizados. Cada una debe ser
  INDEPENDIENTEMENTE PROBABLE: implementar solo una debe seguir dando un MVP
  utilizable.
-->

### User Story 1 - Identificarse y fijar el contexto antes de navegar (Priority: P1)

Un contable abre la aplicación. Antes de ver ninguna opción debe poder
identificarse; después, en el mismo sitio, elegir con qué empresa y con qué
ejercicio va a trabajar. La aplicación muestra de forma permanente quién es, en
qué empresa está y en qué ejercicio está, de modo que en todo momento sabe
bajo qué identidad y sobre qué años está contabilizando.

**Why this priority**: Sin identidad y sin contexto de empresa y ejercicio
explícitos, el resto de la navegación no significa nada: se puede contabilizar en
la empresa equivocada o en el año equivocado. Es la condición previa de todo lo
demás.

**Independent Test**: Entrar sin credenciales, autenticarse, cambiar de empresa y
de ejercicio, y comprobar que los tres indicadores quedan visibles y que
cualquier pantalla alcanzada desde ahí opera sobre esa empresa y ese ejercicio.
Aporta valor por sí solo aunque no exista rail.

**Nota de dependencia**: FR-001 bloquea toda opción de negocio sin sesión, de modo
que esta historia es también la condición previa de las historias P2 y P3. Es
decir, US2 y US3 solo son demostrables **después** de US1, pero siguen siendo
demostrables por separado una vez que la sesión existe.

**Acceptance Scenarios**:

1. **Given** un usuario sin sesión iniciada, **When** intenta abrir cualquier
   opción de la aplicación, **Then** es llevado a la pantalla de identificación y
   no se le muestra ninguna opción de negocio.
2. **Given** un usuario identificado, **When** entra en la aplicación, **Then**
   ve su nombre, la empresa activa y el ejercicio activo en la misma zona
   visual, antes de cualquier contenido de negocio.
3. **Given** un usuario con acceso a varias empresas, **When** cambia de empresa,
   **Then** queda viendo los datos de la nueva empresa y se recalcula el
   ejercicio activo para esa empresa.
4. **Given** un usuario con acceso a una empresa, **When** inicia sesión, **Then**
   el ejercicio activo es el que le corresponde en esa empresa.

---

### User Story 2 - Moverse entre las seis superficies del programa (Priority: P1)

Un contable recorre el programa mediante seis destinos principales que
corresponden a las áreas del trabajo contable (contabilidad, facturación,
tesorería, informes, fiscal y maestros), y dentro de cada una ve el listado de
sus opciones. En el móvil dispone de los mismos accesos sin atender al tamaño de
pantalla.

**Why this priority**: Hoy el programa expone sus opciones en una lista plana de
24 enlaces y aproximadamente 79 de sus 103 pantallas no son alcanzables desde
ningún menú. Sin navegación, el programa solo se usa si uno ya conoce la
dirección exacta de cada página.

**Independent Test**: Abrir la aplicación y comprobar que los seis destinos son
visibles, que cada uno muestra el listado de sus opciones, y que toda pantalla
del programa se alcanza a través de la navegación sin teclear su dirección.
Requiere US1, porque sin sesión no hay shell que mostrar.

**Acceptance Scenarios**:

1. **Given** un usuario identificado, **When** observa la aplicación en
   escritorio, **Then** ve seis destinos principales siempre visibles sin
   desplazamiento.
2. **Given** un usuario identificado, **When** selecciona un destino, **Then**
   ve el listado de las opciones de esa superficie y un resumen del estado de
   esa área.
3. **Given** un usuario en un dispositivo pequeño, **When** observa la
   aplicación, **Then** dispone de los accesos principales y puede cambiar de
   empresa y de ejercicio sin perder de vista la pantalla actual.
4. **Given** el conjunto completo de pantallas del programa, **When** se recorre
   la navegación, **Then** toda pantalla es alcanzable sin conocer su dirección.

---

### User Story 3 - Facturar en dos ejercicios a la vez sin equivocarse (Priority: P1)

Un contable, a 31 de diciembre, está contabilizando facturas del ejercicio que
termina y del que empieza. Cambia de ejercicio para registrar cada una, y en
todo momento sabe en cuál está: el ejercicio que no es el actual se le avisa de
forma visible, y ve cuántos asientos lleva en cada uno antes de decidir.

**Why this priority**: Es el caso que motiva la necesidad de un contexto de ejercicio.
Hoy el ejercicio no es un contexto: cada pantalla lo pide por separado, y
registrar en el año equivocado es un error costoso y difícil de detectar
después.

**Independent Test**: Con dos ejercicios abiertos, alternar entre ambos al
registrar asientos y comprobar que cada asiento queda en el ejercicio mostrado
en ese momento, que el ejercicio anterior se distingue visualmente y que
intentar escribir en un ejercicio cerrado se rechaza con un aviso comprensible.
Requiere US1, porque el selector de ejercicio vive en la zona de contexto.

**Acceptance Scenarios**:

1. **Given** un ejercicio anterior abierto y el ejercicio actual, **When** el
   usuario selecciona el anterior, **Then** la aplicación lo distingue de forma
   visible del actual.
2. **Given** el selector de ejercicio abierto, **When** el usuario lo consulta,
   **Then** ve cuántos asientos hay registrados en cada ejercicio.
3. **Given** un ejercicio seleccionado, **When** el usuario registra un asiento,
   **Then** el asiento queda imputado al ejercicio que está seleccionado y no a
   otro.
4. **Given** un ejercicio cerrado, **When** el usuario intenta registrar un
   asiento, **Then** la operación se rechaza y se le explica que el ejercicio
   está cerrado.
5. **Given** un ejercicio seleccionado, **When** el usuario abre una pantalla que
   permite elegir otro ejercicio, **Then** la elección explícita prevalece sobre
   el ejercicio activo.

---

### User Story 4 - Llevar a sus propias opciones de acceso directo (Priority: P2)

Cada persona marca como favoritos las opciones que más usa, que varían según su
puesto: el de cobros marca vencimientos y conciliación, el de dirección marca
informes y presupuestos. Sus favoritos aparecen en un lugar propio, sin
alterar el orden principal del programa, y desapareyen de la vista cuando deja
de tener acceso a ellos sin perderse por ello.

**Why this priority**: Mejora la velocidad de uso diario, pero el programa ya es
utilizable sin ella. Es la historia que justifica que la navegación sea
personalizable y no idéntica para todos.

**Independent Test**: Marcar dos opciones como favoritas, comprobar que aparecen
en su sección, que persisten al volver a entrar, y que tras perder el permiso
deja de mostrarse pero se conserva.

**Acceptance Scenarios**:

1. **Given** un usuario sin favoritos, **When** marca una opción como favorita,
   **Then** aparece en su sección de favoritos y se conserva al volver a entrar.
2. **Given** un usuario con favoritos, **When** el sistema le revoca el acceso a
   una de ellas, **Then** deja de mostrarse pero no se borra, de modo que
   reaparece si recupera el acceso.
3. **Given** un usuario con favoritos en más de una empresa, **When** cambia de
   empresa, **Then** ve los favoritos de la empresa en la que está.
4. **Given** un usuario con favoritos, **When** los consulta en un dispositivo
   pequeño, **Then** los encuentra en el mismo lugar que en escritorio.
5. **Given** un usuario con favoritos, **When** usa la aplicación, **Then** el
   orden principal de los destinos no cambia según cuáles sean sus favoritos.

---

### User Story 5 - Llegar directamente al resumen de cada área (Priority: P2)

Al entrar en una superficie, el usuario ve no solo el listado de opciones sino un
resumen del estado de esa área: cuántos asientos lleva el ejercicio, qué hay
pendiente, qué avisos tiene.

**Why this priority**: Aporta valor real de orientación, pero la navegación ya
funciona sin resúmenes. Se puede añadir después sin tocar la estructura.

**Independent Test**: Entrar en cada una de las superficies y comprobar que
muestra un resumen con datos del ejercicio activo y que ese resumen se actualiza
al cambiar de empresa o de ejercicio.

**Acceptance Scenarios**:

1. **Given** un usuario en la superficie de Contabilidad, **When** entra en ella,
   **Then** ve cuántos asientos hay en el ejercicio activo y cuál fue el
   último.
2. **Given** un usuario en la superficie de Tesorería, **When** entra en ella,
   **Then** ve el saldo de tesorería y los vencimientos próximos.
3. **Given** un usuario que cambia de ejercicio, **When** vuelve a entrar en una
   superficie, **Then** el resumen refleja el ejercicio nuevo.
4. **Given** un usuario en Maestros, **When** entra en ella, **Then** ve el
   listado de empresas de su ámbito y su detalle.

---

### User Story 6 - No perder el trabajo por rutas que cambian de sitio (Priority: P3)

Cuando una opción cambia de ubicación, quien la tenía marcada o enlazada sigue
llegando a ella.

**Why this priority**: Es mantenimiento de lo ya construido y solo afecta a
direcciones antiguas. Importante, pero no bloquea a nadie.

**Independent Test**: Intentar abrir las direcciones antiguas de las opciones
reubicadas y comprobar que llevan a la ubicación vigente.

**Acceptance Scenarios**:

1. **Given** una dirección antigua de una opción reubicada, **When** se abre,
   **Then** se llega a la ubicación vigente.
2. **Given** un usuario con un favorito en una opción reubicada, **When** cambia
   de empresa, **Then** el favorito sigue resolviendo a la ubicación vigente.

---

### Edge Cases

- El usuario tiene acceso a una empresa cuyo ejercicio activo no existe: la
  aplicación lo comunica y no le permite escribir en un ejercicio inexistente.
- El usuario pertenece a una empresa sin ningún ejercicio creado.
- El ejercicio activo del ejercicio anterior se cierra mientras el usuario
  está trabajando: la aplicación le avisa y pasa al ejercicio vigente.
- El usuario abre en un pestaña el ejercicio 2025 y en otra el 2026 y escribe en
  ambas: cada escritura va a su ejercicio.
- El usuario pierde el acceso a una superficie completa por cambio de rol: los
  destinos que ya no puede usar desaparecen, sin dejar accesos rotos.
- El ejercicio seleccionado pertenece a otra empresa: se rechaza y se vuelve al
  ejercicio válido de la empresa activa.
- El usuario llega a una pantalla sin contexto (por ejemplo, escribiendo su
  dirección): la aplicación no le deja registrar nada hasta que hay sesión,
  empresa y ejercicio.
- Una opción sigue presente como favorito aunque su destino se haya reubicado.
- La lista de favoritos supera el máximo visible: la aplicación MUST **guardar** el
  favorito marcado, MUST mostrar solo los 5 primeros por orden y MUST avisar de que
  hay más. El favorito que no se muestra MUST NOT perderse: si el usuario desmarca
  otro, MUST reaparecer.
- El usuario cierra sesión desde el menú de sesión: al volver a entrar recupera
  empresa, ejercicio y favoritos. (Actualizado 2026-09-29: hasta esa fecha el
  escenario era imposible de reproducir, porque cerrar sesión no existía en
  ninguna parte de la aplicación.)
- La consulta de contexto no puede resolverse: la aplicación MUST comunicar que no
  puede determinar el contexto y MUST impedir cualquier registro, en lugar de
  asumir una empresa o un ejercicio.
- La sesión caduca mientras el usuario está rellenando un registro: la aplicación
  MUST conservar lo introducido y MUST ofrecer reidentificarse sin perderlo.
- El usuario solo tiene acceso a una empresa: el selector de empresa MUST quedar
  visible pero sin opciones que cambiar, en lugar de ocultarse y desplazar el
  resto de la zona de contexto. Lo mismo en el menú de sesión: MUST decirlo, en
  lugar de abrir una lista de un solo elemento.
- El usuario cierra sesión desde el menú: MUST borrarse el ejercicio seleccionado
  **antes** que la empresa activa, porque el almacén de ejercicios está indexado
  por empresa. Al revés, el ejercicio que eligió el usuario anterior se queda
  guardado y el siguiente usuario de la misma máquina abre la aplicación en él
  (añadido 2026-09-29).
- El usuario no puede acceder a ninguna superficie por cambio de rol: la aplicación
  MUST retirar los destinos inaccesibles y MUST indicar que no hay superficies
  disponibles, sin dejar ningún destino roto.

## Requirements *(mandatory)*

### Functional Requirements

**Contexto e identidad**

- **FR-001**: La aplicación MUST impedir el acceso a cualquier opción de negocio
  sin una sesión de usuario identificada, y MUST dirigir a la identificación en
  ese caso.
- **FR-002**: La aplicación MUST mostrar de forma permanente y conjunta la
  identidad del usuario, la empresa activa y el ejercicio activo, en una misma
  zona de la interfaz situada antes del contenido de negocio.
- **FR-003**: La aplicación MUST ofrecer la selección de empresa y la selección de
  ejercicio tanto en escritorio como en dispositivo pequeño.
- **FR-032** (añadido 2026-09-29): La zona de contexto MUST ofrecer, tanto en
  escritorio como en dispositivo pequeño, un **menú de sesión** que reúna las tres
  acciones de identidad: cambiar de empresa, cambiar de ejercicio y **cerrar
  sesión**. Cerrar sesión MUST vaciar las credenciales del cliente (el token de
  `localStorage` y la cookie de sesión) y MUST dirigir a la identificación.
  La redacción original de FR-002 hablaba de identidad, empresa y ejercicio como
  **información** que se muestra, y no como **acciones**: por eso la aplicación
  cerró sin ninguna forma de cerrar sesión, que es exactamente lo que un usuario
  espera encontrar en el sitio donde está su nombre.
- **FR-004**: Un cambio de empresa MUST recalcular el contexto sin arrastrar
  datos de la empresa anterior, y MUST reevaluar el ejercicio activo de la
  empresa nueva.
- **FR-005**: El ejercicio activo MUST determinarse a partir de la empresa activa
  y MUST validarse contra ella; un ejercicio que no pertenece a la empresa activa
  MUST rechazarse.
- **FR-006**: La aplicación MUST exponer un único punto de consulta del contexto
  que devuelva identidad, empresas y ejercicios de la empresa activa, con el
  permiso mínimo que ya posea cualquier usuario con acceso a la contabilidad.
- **FR-007**: Cuando el ejercicio seleccionado se elija de forma explícita en una
  pantalla, esa elección MUST prevalecer sobre el ejercicio activo.

**Navegación por superficies**

- **FR-008**: La aplicación MUST organizar las opciones del programa en seis
  superficies: Contabilidad, Facturación, Tesorería, Informes, Fiscal y Maestros.
- **FR-009**: Los seis destinos MUST ser visibles de forma permanente en
  escritorio, sin desplazamiento, y en un orden estable e independiente del uso.
- **FR-010**: Cada superficie MUST ofrecer una pantalla de inicio con el listado
  de sus opciones y un resumen de su estado.
- **FR-011**: En dispositivo pequeño la aplicación MUST ofrecer una barra inferior
  con 4 destinos más un acceso «Más», MUST mantener los mismos destinos que en
  escritorio, y MUST permitir cambiar de empresa y de ejercicio sin abandonar la
  pantalla en curso.
- **FR-012**: Toda pantalla del programa MUST ser alcanzable desde la navegación,
  sin necesidad de conocer su dirección.
- **FR-013**: Las acciones de creación MUST presentarse como acciones de la
  pantalla en la que se aplican, y MUST NOT aparecer como destinos de
  navegación.
- **FR-014**: La aplicación MUST ofrecer una única ubicación vigente por opción;
  cuando una opción se reubique, las direcciones anteriores MUST llevar a la
  ubicación vigente.
- **FR-015**: Las etiquetas de navegación MUST ser comprensibles sin
  conocimiento previo del programa y MUST NOT presentar acrónimos o
  códigos de modelo como única denominación de una superficie.

**Ejercicio activo y cierre**

- **FR-016**: La aplicación MUST distinguir visualmente el ejercicio vigente, un
  ejercicio anterior abierto, un ejercicio con apertura y un ejercicio cerrado.
- **FR-017**: La aplicación MUST mostrar el número de asientos registrados en cada
  ejercicio seleccionable, junto al nombre del ejercicio.
- **FR-018**: La aplicación MUST rechazar la escritura en un ejercicio cerrado y
  MUST comunicar el motivo al usuario.
- **FR-019**: La aplicación MUST presentar como cerrados aquellos ejercicios que
  cualquiera de sus fuentes de estado marque como cerrados, de modo que la
  información mostrada y la posibilidad de escribir nunca discrepen.
- **FR-020**: Al cerrar un ejercicio que estaba activo, la aplicación MUST
  desviar al usuario al ejercicio vigente y comunicarlo.

**Favoritos**

- **FR-021**: Cada usuario MUST poder marcar y desmarcar opciones como
  favoritas, y el conjunto MUST conservarse entre sesiones.
- **FR-022**: Los favoritos MUST pertenecer a cada usuario, ser independientes entre
  usuarios y variar por empresa, de modo que un usuario vea sus favoritos de la
  empresa en la que se encuentra.
- **FR-023**: Los favoritos MUST presentarse en una sección propia que MUST NOT
  alterar el orden ni la presencia de los destinos principales.
- **FR-024**: Un favorito al que el usuario pierde acceso MUST ocultarse y MUST
  conservarse, de modo que reaparezca si recupera el acceso.
- **FR-025**: La aplicación MUST limitar los favoritos visibles a un máximo de 5 y MUST
  NOT perder los que excedan ese límite ni su orden.
- **FR-026**: Un favorito MUST referirse a la opción que representa y MUST seguir
  resolviendo a su ubicación vigente aunque la opción se reubique.
- **FR-027**: Un usuario sin favoritos MUST ver el listado de opciones de la
  superficie sin estados vacíos ni Messages de ausencia de configuración.

**Maestros y empresas**

- **FR-028**: La aplicación MUST ofrecer en Maestros el listado de empresas del
  ámbito del usuario, con su detalle y su alta.
- **FR-029**: La aplicación MUST ofrecer en Maestros un ajuste de configuración del
  sistema de información fiscal que hoy solo existe como operación interna.

**Accesibilidad de la navegación**

- **FR-030**: Toda la navegación MUST ser operable íntegramente por teclado, con un
  orden de tabulación desde la zona de contexto hacia el contenido de la pantalla, y
  MUST NOT capturar atajos que la pantalla de entrada contable ya use.
- **FR-031**: Cada elemento navegable MUST tener foco visible, y el estado del
  ejercicio MUST NOT transmitirse solo por color: todo estado MUST llevar una etiqueta
  de texto legible sin depender del color.

### Key Entities

- **Contexto de sesión**: Estado de la sesión del usuario en un momento dado,
  compuesto por su identidad, sus roles, la empresa activa y el ejercicio
  activo. Es de lectura y de cambio explícito, no de negocio.
- **Superficie**: Agrupación de opciones del programa con un propósito contable
  común, que agrupa destinos, pantallas de inicio y un resumen propio.
- **Destino**: Referencia estable a una opción de la aplicación, identificada por
  una clave y no por su dirección, para que sobreviva a reubicaciones. El término
  «opción» que aparece en los requisitos es el nombre de usuario de un destino, no
  un concepto distinto: una opción **es** un destino.
- **Ejercicio**: Periodo contable de una empresa, con su estado (vigente,
  anterior abierto, con apertura, cerrado) y su recuento de asientos.
- **Favorito**: Vinculo entre un usuario, una empresa y un destino, con su
  posición en el orden elegido por el usuario.
- **Resumen de superficie**: Indicadores del estado de un área para el ejercicio
  activo, derivados de la información ya existente.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100 % de las pantallas existentes es alcanzable desde la
  navegación, verificado de forma automática, sin ninguna Known excepción.
- **SC-002**: Un usuario encuentra la opción que busca en un máximo de dos
  movimientos desde la pantalla de inicio, en el 90 % de las opciones del
  programa. **Método**: se mide sobre el mapa de superficies, que es una taxonomía
  finita y cerrada; se considera alcanzado si el 90 % de los destinos se
  alcanzables desde la landing de su superficie en un movimiento, o desde la landing
  de Contabilidad en dos. No se mide por muestreo de usuarios.
- **SC-003**: Ningún asiento puede registrarse en un ejercicio distinto del que la
  interfaz muestra como activo, verificado con pruebas automatizadas.
- **SC-004**: El 100 % de las pantallas con escritura rechazan la operación cuando
  el ejercicio está cerrado, sin que el usuario necesite conocer el motivo
  interno.
- **SC-005**: Un usuario con acceso a más de una empresa cambia de empresa y ve
  datos coherentes con la nueva en su primera pantalla, en el 100 % de los casos.
- **SC-006**: La zona de contexto (identidad, empresa, ejercicio) es visible en el
  100 % de las pantallas de negocio.
- **SC-007**: Cada usuario puede fijar hasta 5 favoritos, y su selección se
  conserva al cerrar y volver a abrir la sesión en el 100 % de los casos.
- **SC-008**: Un favorito deja de mostrarse cuando se pierde el acceso y reaparece
  al recuperarlo, verificado en el 100 % de los casos.
- **SC-009**: En dispositivo pequeño, cambiar de empresa o de ejercicio y volver
  a la pantalla en curso se completa en un máximo de 3 acciones.
- **SC-010**: Toda dirección antigua de una opción reubicada lleva a su
  ubicación vigente, verificado para el 100 % de las opciones reubicadas.
- **SC-011**: Ninguna opción de la aplicación queda fuera de una superficie, y la
  comprobación automática que lo verifica se ejecuta en **toda** ejecución de la
  suite de pruebas, de modo que una pantalla sin asignar rompe la construcción en
  el momento en que se introduce.
- **SC-012**: Un usuario sin favoritos configurados ve el listado completo de su
  superficie, sin mensajes de ausencia de configuración.
- **SC-013**: Cambiar de empresa o de ejercicio y volver a ver la aplicación
  operativa tarda menos de un segundo en el 95 % de los casos. El volumen de datos
  con el que se mide no forma parte del criterio: lo fija la prueba de rendimiento.

## Assumptions

- El sistema de identificación y de permisos existente se reutiliza sin
  cambios en su modelo de datos; esta feature no altera quién puede hacer qué.
- La gestión de altas de usuario, cambio obligatorio de contraseña y registro de
  quién realiza cada apunte quedan expresamente fuera de esta feature, y se
  abordarán en una feature posterior de seguridad.
- La pertenencia del ejercicio a la empresa se toma de los registros de
  ejercicio ya existentes; cuando dos fuentes de estado discrepen, se
  prevalece el estado más restrictivo.
- El resumen de cada superficie se apoya en la información ya disponible; si
  faltara algún dato, se añade la consulta necesaria con los mismos permisos que
  la superficie.
- Los favoritos se guardan por usuario y por empresa, de modo que un mismo
  usuario puede tener un conjunto distinto en cada empresa.
- El número de seis superficies y su orden son una decisión de producto tomada,
  no una preferencia pendiente de validar con usuarios.
- La reubicación de opciones conserva la dirección canónica definitiva; las
  direcciones anteriores solo se mantienen como vía de compatibilidad, no como
  ubicaciones preferidas.
- En dispositivo pequeño se mantienen los mismos destinos que en escritorio; lo
  que cambia es la presentación, no el conjunto de opciones.
- Las etiquetas en castellano pueden acompañarse de siglas cuando la sigla sea de
  uso habitual en el sector y se acompañe siempre de su significado.
- Tres requisitos delegan a propósito una decisión técnica en el plan, y esa
  delegación es intencionada y no una omisión: FR-006 (qué permiso mínimo protege
  la consulta de contexto), FR-011 antes de la cuantificación ahora resuelta en 4 más
  «Más», y FR-015 (qué siglas se aceptan). El plan fija las tres; el requisito fija el
  criterio, que es lo que debe ser comprobable.
- Los 4 destinos de la barra inferior en dispositivo pequeño los elige el producto
  entre los 6; el requisito fija el número y que sean los mismos que en escritorio,
  no la elección concreta, que queda como decisión de producto en el plan.
