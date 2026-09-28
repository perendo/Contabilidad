# Feature Specification: Documentos adjuntos al asiento (diario contable)

**Feature Branch**: `030-documentos-asiento`

**Created**: 2026-09-26

**Status**: Draft

**Input**: User description: "Incluir documentos (uno o mas) en el diario en formato imagen o en formato pdf"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Adjuntar documentos justificantes a un asiento (Priority: P1)

El usuario contable abre un asiento del diario (una factura de compra, un justificante
bancario, un recibo) y adjunta uno o varios documentos que lo respaldan: el PDF de la
factura del proveedor, la foto o el escaneo del justificante, el extracto bancario. A
partir de ese momento el asiento deja de ser una cifra sin contexto y pasa a ser
evidencia verificable que un auditor puede abrir desde la propia aplicación.

**Why this priority**: Es el valor central de la funcionalidad y lo que la justifica
frente a las demás. Sin adjuntar, el diario sigue siendo utilizable pero no auditable;
con la adjunción, el sistema gana trazabilidad documental que la imposición no exige
hoy en ningún caso.

**Independent Test**: Dado un asiento del diario, cuando el usuario selecciona uno o
varios ficheros (imagen o PDF) y confirma la carga, entonces el asiento muestra los
documentos adjuntos, cada uno con su nombre, formato, tamaño y huella, y el contenido
descargado coincide con el fichero original.

**Acceptance Scenarios**:

1. **Given** un asiento del diario de la empresa activa, **When** el usuario selecciona
   tres ficheros a la vez (un PDF y dos imágenes) y confirma, **Then** los tres quedan
   adjuntos al mismo asiento y aparecen listados en su detalle.
2. **Given** un asiento del diario, **When** el usuario adjunta un fichero en formato
   admitido y elige su tipo (factura, recibo, extracto, justificante) y una
   descripción, **Then** esa clasificación queda guardada y se muestra junto al documento.
3. **Given** un asiento del diario, **When** el usuario adjunta un fichero de un
   formato no admitido o que supera el tamaño máximo, **Then** el sistema lo rechaza con
   un mensaje claro y no queda nada a medias.
4. **Given** un asiento ya contabilizado al que todavía no se le ha adjuntado el soporte,
   **When** el usuario adjunta el PDF o la imagen del justificante, **Then** el documento
   queda vinculado al asiento y las cifras del asiento permanecen idénticas.

---

### User Story 2 - Consultar y descargar los documentos de un asiento (Priority: P2)

El usuario que revisa el diario (o el auditor que lo recibe) abre el detalle de un
asiento y ve cuántos documentos tiene adjuntos, los previsualiza y los descarga sin
salir de la aplicación ni perder la sesión de trabajo. También puede localizar los
documentos de un ejercicio concreto, porque en una empresa con mucho volumen no recuerda
qué asiento tenía el justificante buscado.

**Why this priority**: Un documento que se adjunta pero no se puede volver a abrir no
aporta valor: la prueba de auditoría exige poder examinar el soporte en el momento en
que se revisa el asiento.

**Independent Test**: Dado un asiento con documentos adjuntos, cuando el usuario abre su
detalle y descarga cada documento, entonces el contenido obtenido es idéntico al original
(la huella coincide) y la descarga se realiza de forma autenticada.

**Acceptance Scenarios**:

1. **Given** un asiento con dos documentos adjuntos, **When** el usuario abre su detalle,
   **Then** ve el número de documentos y puede abrir o descargar cada uno individualmente.
2. **Given** un documento ya adjuntado, **When** el usuario lo descarga, **Then** la
   huella del contenido descargado coincide con la registrada en el alta.
3. **Given** una empresa con muchos asientos, **When** el usuario filtra los documentos
   por ejercicio y/o por tipo, **Then** obtiene el listado de los documentos de la empresa
   activa con su asiento asociado.

---

### User Story 3 - Integridad, trazabilidad e inalterabilidad del soporte (Priority: P3)

El responsable contable necesita poder demostrar que los soportes del diario no se han
alterado ni se han retirado de forma silenciosa. Cada documento queda identificado con
una huella verificable y con su autor, fecha y tipo; toda alta y toda baja queda
registrada de forma inmutable; y el contenido de un documento jamás puede ser sustituido
por otro.

**Why this priority**: Es la garantía de confianza que convierte a los adjuntos en
prueba válida y no en un simple almacén de ficheros. Sin ella, la funcionalidad pierde su
valor en una revisión o inspección.

**Independent Test**: Dados dos documentos, cuando se comprueban sus huellas, entonces
son distintas; y si se intenta reemplazar el contenido de un documento ya adjuntado,
entonces el sistema lo rechaza y el contenido original permanece intacto.

**Acceptance Scenarios**:

1. **Given** un documento adjuntado, **When** se intenta subir otro fichero sobre él,
   **Then** el sistema rechaza la operación y el contenido original permanece intacto.
2. **Given** un documento ya adjuntado a un asiento, **When** el usuario intenta adjuntar
   de nuevo ese mismo fichero (misma huella) a ese mismo asiento, **Then** el sistema lo
   rechaza por duplicado.
3. **Given** altas y bajas de documentos realizadas, **When** se consulta el rastro de
   auditoría, **Then** cada operación figura con usuario, fecha y hora, origen, operación
   y documento afectado, y ninguna de esas entradas puede modificarse ni borrarse.
4. **Given** un documento dado de baja, **When** se solicita su recuperación, **Then** el
   contenido y la huella siguen disponibles y son idénticos a los del alta.

---

### Edge Cases

- **Extensión engañosa**: un fichero llamado `factura.pdf` que en realidad es una imagen.
  → Se rechaza: el contenido debe corresponder al formato declarado.
- **Fichero inservible**: PDF corrupto, PDF protegido con contraseña o imagen con los
  datos recortados e ilegibles. → Se rechaza con un motivo claro, aunque la extensión
  declarada sea válida.
- **Fichero vacío o de tamaño cero**. → Se rechaza por tamaño inválido.
- **Nombre de fichero con acentos, eñes, espacios o longitud excesiva**. → Se conserva el
  nombre original tal cual se introdujo y se entrega en la descarga sin corromperlo.
- **Selección múltiple con un fichero fallido**. → Los documentos válidos quedan
  adjuntados y el usuario recibe el detalle de los rechazados y su motivo; no se descarta
  el trabajo ya validado ni quedan registros incompletos.
- **Mismo fichero justificante en dos asientos distintos**. → Permitido: un mismo soporte
  puede justificar dos asientos; la detección de duplicados solo actúa dentro del mismo
  asiento.
- **Asiento anulado o rectificado después de adjuntar documentos**. → El documento
  permanece vinculado al asiento original (que es inmutable) y el usuario puede
  opcionalmente vincular ese mismo documento al asiento rectificativo.
- **Ejercicio cerrado o libro legalizado**. → Adjuntar un documento no altera las cifras ni
  la partida doble del asiento, por lo que no se bloquea por ejercicio cerrado ni por
  legalización; sí queda registrado en la auditoría. (Ver FR-010 y FR-015.)
- **Baja solicitada sobre un asiento ya contabilizado**. → El sistema la rechaza: el
  soporte de un asiento asentado no se retira. Si la evidencia es incorrecta, la vía
  correcta es la anulación o rectificación del asiento.
- **Documento con datos personales de terceros**. → El documento se conserva íntegro por
  obligación de conservación, pero su acceso queda sujeto a los permisos del usuario y
  siempre al aislamiento por empresa.
- **Espacio de almacenamiento de la empresa agotado**. → La carga se rechaza con un
  mensaje comprensible y no queda ningún documento a medias.
- **Usuario sin permiso**. → No ve la opción de adjuntar ni de dar de baja, y el sistema
  rechaza igualmente sus intentos aunque acceda por otra vía.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Los documentos MUST poder anclarse a los asientos del diario contable. Los
  demás puntos de anclaje del sistema (facturas, vencimientos, extractos bancarios,
  modelos fiscales) quedan **fuera de alcance**: la única ruta de alta es
  `POST /api/v1/documentos/asiento/{id}`, de modo que no existe forma de intentarlo y la
  restriccion no es observable en la API.
- **FR-002**: El sistema MUST admitir documentos en formato PDF y en formato imagen
  (JPEG, PNG y TIFF), y MUST rechazar con un mensaje explícito cualquier otro formato.
- **FR-003**: El sistema MUST aplicar un límite de tamaño por documento (10 MB por
  defecto) y MUST rechazar los documentos que lo superen.
- **FR-004**: Cada documento MUST pertenecer a un único asiento y a la empresa activa de
  la sesión; MUST rechazarse el anclaje a un asiento de otra empresa.
- **FR-005**: El sistema MUST registrar por cada documento el nombre original, el formato,
  el tamaño, la huella de integridad, la fecha y hora de alta en UTC, el usuario que lo
  adjuntó, un tipo de documento (factura, recibo, extracto, justificante u otro) y una
  descripción opcional; además el tipo de contenido y la extensión, **derivados de la
  firma del fichero** y no de lo que declare el cliente.
- **FR-006**: El sistema MUST detectar los duplicados por huella dentro de un mismo
  asiento y MUST rechazarlos; el mismo fichero MAY adjuntarse a asientos distintos.
- **FR-007**: El sistema MUST permitir consultar y descargar cada documento de un asiento
  desde el detalle del asiento, de forma autenticada y sin perder la sesión.
- **FR-008**: El detalle de un asiento MUST mostrar el número de documentos adjuntos y
  MUST permitir abrir directamente cada uno de ellos.
- **FR-009**: El contenido, el nombre y la huella de un documento adjuntado MUST ser
  inalterables: toda sustitución o sobrescritura MUST rechazarse.
- **FR-010**: Adjuntar documentos MUST ser permitido tanto en un asiento en borrador como
  en un asiento ya contabilizado, porque la evidencia puede incorporarse después de
  contabilizar. Dar de baja un documento MUST permitirse **únicamente** mientras el asiento esté
  en borrador; sobre un asiento `POSTED` o `CANCELLED` MUST rechazarse, de modo que la
  evidencia de un asiento asentado o anulado no puede retirarse.
- **FR-011**: El sistema MUST registrar de forma inmutable toda alta y toda baja de
  documentos (usuario, fecha y hora en UTC, dirección de origen, operación, documento y
  asiento afectados), y ese registro MUST conservarse aunque el documento se dé de baja.
- **FR-012**: La baja de un documento MUST ser lógica y MUST NOT suprimir su contenido: el
  documento queda marcado como dado de baja con su motivo, su responsable y su fecha, y su
  contenido y su huella permanecen recuperables durante el plazo legal de conservación de
  los soportes contables, **seis años** (art. 30 LGT), parametrizable con
  `documento_plazo_conservacion_anos`. El derecho de supresión de datos personales MUST NOT
  eliminar el
  soporte contable; se atiende, en su caso, restringiendo la visibilidad según los permisos
  del usuario.
- **FR-013**: Ningún documento de una empresa MUST ser visible, descargable, adjuntable ni
  bajable desde otra empresa; el sistema MUST negar el acceso también cuando se conozca el
  identificador del documento o del asiento.
- **FR-014**: El sistema MUST verificar que el contenido del fichero corresponde al formato
  declarado y MUST rechazar los ficheros dañados, protegidos o vacíos.
- **FR-015**: Adjuntar o dar de baja un documento MUST NOT alterar los datos contables del
  asiento (importes, Debe, Haber, número, fecha y estado contable), y el asiento MUST
  seguir cuadrando exactamente.
- **FR-016**: El sistema MUST exigir un permiso explícito para adjuntar documentos y un
  permiso explícito y diferenciable para darlos de baja.
- **FR-017**: El sistema MUST permitir listar los documentos de la empresa activa con
  filtros por asiento, por ejercicio y por tipo de documento.
- **FR-018**: Si en una carga de varios documentos alguno es rechazado, el sistema MUST
  conservar los documentos aceptados e informar al usuario del rechazo y su motivo, sin
  dejar registros incompletos.
- **FR-019**: El sistema MUST ofrecer una vía de consulta de los documentos tanto desde el
  propio asiento como desde el listado global, de modo que la evidencia sea localizable
  sin conocer de antemano el número de asiento.
- **FR-020**: La adjunción de documentos MUST ser siempre opcional: un asiento MUST poder
  existir, contabilizarse, cerrarse, formularse, exportarse y liquidarse sin ningún documento
  adjunto. La ausencia de documentos MUST NOT bloquear ni condicionar ninguna operación
  contable, fiscal ni de cierre, y el sistema MUST NOT exigir la adjunción en ningún flujo.

### Key Entities

- **Documento del asiento**: fichero de evidencia (PDF o imagen) asociado a un asiento.
  Atributos clave: nombre original, formato, tamaño, huella de integridad, tipo de
  documento, descripción, fecha de alta (UTC), usuario que lo adjuntó y estado (activo o
  dado de baja, con su motivo, su responsable y su fecha de baja).
- **Asiento contable**: entidad ya existente del diario contable a la que se anclan uno o
  varios documentos. Relación uno-a-muchos.
- **Rastro de trazabilidad del documento**: registro inmutable de cada alta y cada baja,
  con autor, fecha y hora en UTC, origen, operación y elementos afectados.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El usuario adjunta un documento a un asiento en menos de 60 segundos sin
  abandonar la pantalla del asiento. *Criterio de usuario, no automatizado: depende
  del ancho de banda y del dispositivo, y ninguna tarea mide tiempo de pared.*
- **SC-002**: El 100 % de los documentos adjuntados se vuelven a consultar y a descargar
  íntegros, con huella coincidente con la del alta, en menos de 3 segundos.
- **SC-003**: El 0 % de los documentos de una empresa resulta visible, descargable,
  adjuntable o bajable desde otra empresa, incluso conocida la referencia del documento.
- **SC-004**: El 100 % de los documentos quedan identificados con huella verificable, autor,
  fecha y hora, tipo de documento y asiento asociado.
- **SC-005**: El 100 % de los intentos de sustituir o sobrescribir el contenido, el nombre
  o la huella de un documento ya adjuntado se rechazan sin alterar el original.
- **SC-006**: El 100 % de los intentos de alta o baja de documentos quedan registrados en
  una traza inmutable e insuprimible.
- **SC-007**: El 100 % de las operaciones de adjuntar o dar de baja documentos respeta la
  partida doble: el asiento mantiene su cuadre antes y después de la operación.
- **SC-008**: Un asiento admite al menos 20 documentos adjuntos sin que la consulta del
  detalle se vuelva inutilizable. Verificable contando los items que devuelve
  `GET /asiento/{id}` con 20 documentos, no "por perceccion".
- **SC-009**: El 100 % de los ficheros de formato no admitido, de tamaño excesivo,
  duplicados o con contenido incoherente con su formato son rechazados con un mensaje
  comprensible.
- **SC-010**: El usuario localiza el documento que busca partiendo de un ejercicio o de
  un tipo, sin recordar el número de asiento, en el 100 % de los casos en que existe.
- **SC-011**: El 100 % de los intentos de baja sobre un asiento ya contabilizado se
  rechazan, y el 100 % de los documentos dados de baja conservan su contenido y su huella
  durante el plazo legal de conservación.
- **SC-012**: El 100 % de los asientos sin documentos adjuntos completan su ciclo de vida
  normal (contabilizar, corregir, cerrar y exportar) sin ninguna restricción adicional, y
  el 0 % de las operaciones del sistema exige la existencia de al menos un documento.

## Assumptions

- **Formatos**: se admiten PDF (incluidos los multipágina), JPEG, PNG y TIFF. Una imagen
  multipágina es un único documento.
- **Límites**: 10 MB por documento y ningún límite adicional de número de documentos por
  asiento (se garantiza al menos 20, según SC-008).
- **Empresa activa**: se deriva de la sesión autenticada; el cliente nunca indica la
  empresa, y el documento se almacena y se filtra siempre por la empresa activa.
- **Carga**: los ficheros se cargan individualmente o en selección múltiple; no se admiten
  carpetas ni archivos comprimidos en esta versión.
- **Sin reconocimiento de texto**: no se extrae texto ni se realiza OCR de los documentos;
  la clasificación (tipo) la indica el usuario.
- **Importes del documento**: el documento no tiene importe propio. Si el usuario indica un
  importe informativo, se almacena con precisión decimal de 4 decimales y MUST NOT alterar
  ni sustituir las cifras del asiento.
- **Firmas**: no se valida ni se exige firma digital del documento.
- **Reutilización**: se reutiliza el rastro de auditoría ya existente en el sistema
  (usuario, UTC, dirección IP, operación y contenido de la operación) y las reglas de
  permisos por rol vigentes.
- **Baja de documentos**: la baja es siempre lógica y solo se permite sobre asientos en
  borrador (FR-010 y FR-012). El contenido se conserva durante el plazo legal de
  conservación de los soportes contables; para los datos personales que contenga se
  restringe la visibilidad por permisos, sin suprimir el soporte.
- **Opcionalidad de la adjunción**: adjuntar documentos es siempre opcional. Ningún asiento
  está obligado a tener uno y ninguna operación contable, fiscal o de cierre depende de que
  los tenga; la adjunción aporta evidencia, no habilita el asiento (FR-020, SC-012).
- **Punto de anclaje**: exclusivamente los asientos del diario; facturas, extractos
  bancarios, vencimientos y modelos fiscales quedan fuera de esta versión (FR-001).
- **Constitution alignment**: la adjunción es una operación sobre la evidencia del diario,
  no una modificación de sus cifras; por tanto no altera el invariante de partida doble ni
  la inmutabilidad de los datos contables del asiento.
- **Fuera de alcance**: OCR, firma digital, carga por carpetas o ZIP, clasificación
  automática, integración con gestores documentales externos, y la incorporación
  automática de estos documentos al libro-diario PDF oficial y a la exportación integral del
  tenant, que quedan como ampliación posterior (SPEC-019 y SPEC-029).

## Dependencias

- **SPEC-002** (motor de asientos y diario contable): los asientos son el punto de anclaje
  y su numeración correlativa e inmutabilidad condicionan el diseño.
- **SPEC-003** (multiempresa y empresa activa): origen de la empresa que delimita el
  aislamiento de los documentos.
- **SPEC-005** y **SPEC-029** (importación y exportación): la inclusión de los documentos
  adjuntos en la exportación integral del tenant queda declarada como ampliación; la
  descarga autenticada se apoya en el patrón ya existente.
- **SPEC-015** (matriz de permisos por rol): los permisos de adjuntar y de dar de baja se
  registran en el catálogo de operaciones.
- **SPEC-019** (gestión ONG y libros oficiales): comparte la semántica de fichero con
  huella y contenido inmutable, y es la referencia para cualquier interacción futura con
  la legalización de libros.
