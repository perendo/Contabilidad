# Research: Documentos adjuntos al asiento (SPEC-030)

**Feature**: `specs/030-documentos-asiento/spec.md` · **Date**: 2026-09-26
**Input**: spec.md (FR-001..FR-020, SC-001..SC-012) y aclaracion del usuario: no es obligatorio incluir un documento en cada asiento.

Todas las decisiones de este documento estan resueltas: no quedan NEEDS CLARIFICATION.

---

## D1. Almacen del contenido binario

**Decision**: columna `BYTEA` en PostgreSQL (`LargeBinary` en SQLAlchemy), igual que
`services/reconciliation/importacion.py:62` y `models/ngo/libros.py` ya hacen con
`ExtractoBancario` y `LibroOficial`. Una fila por documento, sin tabla de metadatos aparte.

**Rationale**: el proyecto ya almacena binarios en base de datos en SPEC-013 y SPEC-019. Con
`BYTEA` el aislamiento por tenant, el backup y el borrado son una sola operacion transaccional,
y el cumplimiento de la constitution III no depende de una segunda ruta de acceso al fichero.
La exportacion integral (SPEC-029) tambien gana: los binarios viajan con el mismo `SELECT` que
el resto.

**Alternatives considered**:
- *Sistema de ficheros mas columna con la ruta*: rechazado. Introduce una segunda ruta de
  acceso que hay que aislar por `empresa_id`, se sale del backup transaccional y rompe las
  pruebas en SQLite, que es el banco por defecto de la suite.
- *Almacenamiento de objetos externo (S3/MinIO)*: rechazado para esta version. Anade una
  dependencia de infraestructura y un segundo sistema que autorizar, sin ganancia funcional con
  volumenes de esta escala.

## D2. Tabla propia frente a reutilizar `blob_fichero`

**Decision**: tabla nueva `documento_asiento`, con el modelo en
`backend/src/models/acct/documento.py`. No se amplia `BlobFichero`.

**Rationale**: `BlobFichero` (SPEC-020) es un almacen de contenido sin ciclo de vida: no tiene FK
al asiento, ni estado, ni tipo de documento, ni motivo de baja. Encajar la baja logica y el
anclaje al asiento exigiria columnas casi siempre nulas para los cuatro tipos de blob ya
existentes (`remesa_sepa`, `remesa_csb1919`, `r19`, `c19`). Una tabla propia mantiene el
`TipoBlob` cerrado y no altera el comportamiento ya verificado de SPEC-020.

**Alternatives considered**: *anadir `tipo = documento_asiento` y columnas opcionales a
`BlobFichero`*: rechazado por el mismo motivo.

## D3. Inmutabilidad del contenido en base de datos

**Decision**: trigger `BEFORE UPDATE` que permite modificar unicamente las columnas de baja
(`estado`, `baja_motivo`, `baja_usuario`, `baja_at`) y rechaza cualquier cambio en `contenido`,
`sha256`, `nombre_original`, `journal_entry_id`, `empresa_id`, `tipo_documento`, `descripcion`,
`importe_informativo`, `created_by` y `created_at`. Un trigger `BEFORE DELETE` rechaza siempre
el borrado fisico.

**Rationale**: la constitution II exige que la inmutabilidad se garantice a nivel de base de
datos, no solo en la aplicacion. Pero la spec exige ademas la baja logica (FR-012) y la baja
solo en borrador (FR-010), asi que un trigger append-only puro, como el de `desviacion` en
`017_presupuestos.sql`, bloquearia una operacion legitima. El trigger restringido es el punto
mas cercano a la persistencia que respeta ambas cosas a la vez.

**Alternatives considered**:
- *Append-only puro mas tabla `documento_baja` aparte*: rechazado. Parte la verdad de una fila
  en dos tablas y complica el listado sin ganar inmutabilidad adicional.
- *Solo inmutabilidad en la API*: rechazado. Viola la constitution II de forma explicita.

## D4. Modulo RBAC: reutilizar `acct` en lugar de crear `documentos`

**Decision**: no se crea un modulo nuevo. Se usan las operaciones ya existentes del modulo
`acct`: `ver` (listar, consultar y descargar), `crear` (adjuntar) y `baja` (dar de baja).

**Rationale**: los asientos ya viven bajo `acct` (`api/journal/asientos.py` usa
`require_permission("acct", ...)`) y el catalogo de operaciones ya contiene `ver`, `crear` y
`baja`. FR-016 pide un permiso explicito para adjuntar y un permiso explicito y diferenciable
para darlos de baja: `crear` y `baja` cumplen exactamente ese requisito. Anadir un modulo
`documentos` obligaria a cambiar seis ficheros de forma coherente
(`services/security/catalogo.py`, `migrations/007_rbac.sql`, `db/triggers.py` y tres recuentos
de tests) sin aportar granularidad real, y las specs anteriores que si lo hicieron (`centros`,
`ngo`, `presupuestos`) tampoco lo hicieron.

**Alternatives considered**: *modulo `documentos` propio*: rechazado por coste de mantenimiento
desproporcionado. Queda abierto si en el futuro el gestor documental se independiza con roles
propios.

## D5. Trazabilidad: reutilizar el rastro de auditoria existente

**Decision**: no se crea tabla de trazabilidad. Se usa
`services.audit.registrar_auditoria(db, empresa_id=..., operacion=..., entidad="documento_asiento",
entidad_id=doc.id, payload={...}, usuario=actor, ip=...)`, que escribe en `audit_log`, ya
protegido por los triggers WORM `trg_audit_log_immutable_update` y `_delete` de
`migrations/000_audit_log.sql`.

**Rationale**: `audit_log` ya es inmutable a nivel de base de datos, se escribe en la misma
transaccion ACID que la operacion auditada (el `flush()` del servicio vive dentro del boundary
de `get_db`) y ya registra usuario, timestamp UTC, IP, operacion y payload. FR-011 queda
satisfecho sin duplicar infraestructura. Esto valida el supuesto que la checklist registro en
CHK043.

**Alternatives considered**: *tabla `documento_traza` propia*: rechazado. Duplicaria un mecanismo
WORM ya probado y abriria la puerta a que las dos trazas diverjan.

## D6. Deteccion de duplicados: unicidad incondicional

**Decision**: `UNIQUE (empresa_id, journal_entry_id, sha256)` sin indice parcial.

**Rationale**: FR-006 rechaza el mismo fichero dentro de un mismo asiento. Como la baja es
logica y el contenido se conserva (FR-012), la huella sigue ocupando su sitio: permitir
re-adjuntar tras una baja romperia la unicidad del rastro. Un `UNIQUE` normal es suficiente y
evita la trampa de SPEC-026, donde hicieron falta dos indices parciales porque
`centro_coste_id` es nullable y `NULL` no colisiona en un `UNIQUE` normal.

**Alternatives considered**: *indice parcial `WHERE estado = 'activo'`*: rechazado porque
permitiria re-adjuntar el mismo contenido en el mismo asiento tras una baja, y el rastro de
auditoria no sabria distinguirlo de un documento nuevo.

## D7. Forma de la API: prefijo plano con segmento estatico

**Decision**: paquete `backend/src/api/documentos/` con
`APIRouter(prefix="/api/v1/documentos")` en `__init__.py`, y las rutas del asiento bajo el
segmento estatico `/asiento/{asiento_id}`. Cada historia de usuario aporta un fichero
propio: `adjuntos.py` (POST), `consulta.py` (los cuatro GET) y `bajas.py` (DELETE).

**Rationale**: el detalle de asiento vive hoy en `api/journal/journal.py` (prefijo
`/api/v1/journal`) y en `api/journal/asientos.py` (prefijo `/api/v1/asientos`), y este ultimo ya
declara `GET /{entry_id}`. Anidar los documentos bajo `/api/v1/asientos/{id}/documentos`
exigiria tocar dos routers y resolver el orden de registro frente a la ruta comodin. El segmento
estatico `/asiento/` evita cualquier colision y deja el modulo autocontenido, igual que
`api/ngo/` y `api/treasury/`. El paquete, en vez de un modulo suelto, responde a una necesidad
concreta: con un unico `api/documentos.py` las tres historias de usuario editarian el mismo
fichero y no podrian avanzar en paralelo.

**Alternatives considered**:
- *Router anidado en `asientos.py`*: rechazado por la colision con `GET /{entry_id}`.
- *`POST /documentos?asiento_id=...`*: rechazado; un recurso que depende de otro se referencia
  mejor en la ruta que en la query.

## D8. Validacion de que el contenido corresponde al formato

**Decision**: tres capas, sin analizador de tipos generico.
1. Firma inicial (magic bytes): `%PDF-`, `\xFF\xD8\xFF` (JPEG), `\x89PNG\r\n\x1a\n` (PNG),
   `II*\x00` y `MM\x00*` (TIFF). Implementacion propia, sin dependencia.
2. PDF: `pypdf.PdfReader` para rechazar cifrados y corruptos, y contar paginas.
3. Imagen: `PIL.Image` con `.verify()` y `n_frames` para TIFF multipagina.

**Rationale**: `pypdf` ya es dependencia de runtime declarada en `requirements.txt:14`. `pillow`
esta instalada en el entorno (12.3.0) pero no esta declarada, asi que hay que anadirla. Sin una
de las dos capas FR-014 no es comprobable: la extension sola no prueba nada, y el caso limite
del fichero inservible exige un criterio observable, no una promesa.

**Alternatives considered**:
- *Paquete `filetype`*: rechazado. Cubre menos formatos de los cinco exigidos y anade una
  dependencia para algo que son cuatro comparaciones de bytes.
- *Solo firmas*: rechazado. No detecta un PDF corrupto ni una imagen truncada, que es
  exactamente el caso limite de la spec.

**Impacto en dependencias**: anadir `pillow>=10.0,<13.0` a `requirements.txt` de la raiz. Sin
nuevas dependencias de frontend.

## D9. Multipart: `UploadFile` mas `Form`, sin despacho manual

**Decision**: `Annotated[list[UploadFile], File(...)]` junto a `Annotated[str, Form()]` y
`Annotated[str | None, Form()] = None`, siguiendo el patron de `api/reconciliation.py:111-129`.

**Rationale**: la spec solo admite binarios y un unico content-type. El despacho manual
`await request.form()` que usan `api/presupuestos.py` y `api/catalogo.py` existe porque esas
rutas aceptan CSV-multipart o JSON; aqui no aplica. Mezclar `File()` con un modelo pydantic de
body esta prohibido por el problema documentado en AGENTS.md seccion 14.

**Alternatives considered**: *JSON en base64*: rechazado. Infrla un 33 % el payload y obliga a
decodificar en memoria antes de validar.

## D10. Configuracion por settings, no constantes de modulo

**Decision**: cuatro campos nuevos en `backend/src/config.py`:
`documento_max_bytes: int = 10 * 1024 * 1024`, `documento_max_paginas: int = 200`,
`documento_max_por_asiento: int = 50` y `documento_plazo_conservacion_anos: int = 6`.

**Rationale**: hoy el unico limite de subida del repositorio es la constante `MAX_BYTES` de
`api/importexport.py:36`, sin forma de variarlo por entorno. FR-003 dice 10 MB por defecto, y un
default solo tiene sentido si es configurable. El plazo legal cuantificado cierra el hueco
detectado en la checklist (CHK001): el articulo 30 de la Ley General Tributaria fija seis anos
de conservacion para facturas y justificantes.

**Alternatives considered**: *mantener constantes*: rechazado. No permite operar por entorno sin
tocar codigo.

## D11. La adjuncion es opcional: que NO se implementa

**Decision**: ninguna capa impone la presencia de documentos.
- Sin `NOT NULL`, sin `CHECK` y sin columna de recuento en `journal_entry`.
- Ninguna validacion en `entry_service.asentar`, en el cierre de ejercicio, en la formulacion de
  cuentas anuales ni en la exportacion integral.
- `GET /documentos/asiento/{id}` devuelve `{"items": [], "total": 0}`, nunca 404.
- La interfaz muestra un estado vacio explicito que declara la opcionalidad, para que el usuario
  no interprete la ausencia como un error.

**Rationale**: es la aclaracion expresa del usuario. Convertirla en un requisito implicito, por
ejemplo "no se puede contabilizar sin soporte", seria exactamente el tipo de suposicion que la
fase de clarify pretende evitar. La evidencia aporta valor al asiento, pero el asiento es valido
sin ella (FR-020, SC-012).

**Alternatives considered**: *exigir al menos un documento en asientos de tipo factoring o
conciliacion*: rechazado. Pertenece a otra spec y no se ha pedido.

## D12. Previsualizacion en el navegador, sin nuevas dependencias

**Decision**: la previsualizacion usa una URL de objeto creada en el cliente: `<img>` para JPEG,
PNG y TIFF, y `<iframe>` para PDF, alimentados por el mismo blob autenticado que la descarga. El
boton de descarga guarda el fichero con el nombre original.

**Rationale**: el repositorio no tiene visor de PDF, ni miniaturas, ni ninguna instancia de
`<img>`, `<iframe>`, `<object>` o `window.open`. Anadir `pdf.js` para renderizar seria una
dependencia grande y una superficie de seguridad nueva (el PDF como vector de ataque del
navegador) a cambio de una capacidad que el visor nativo ya ofrece. La URL de objeto garantiza
que el contenido nunca se expone como URL publica, que es el requisito de aislamiento.

**Alternatives considered**:
- *pdf.js*: rechazado por dependencia y superficie de ataque.
- *Solo descarga sin previsualizar*: rechazado. FR-007 pide consultar, no solo recuperar.

## D13. Seleccion multiple en una sola peticion

**Decision**: un unico `<input type="file" multiple>` y una sola peticion multipart con el campo
`files` como lista. La respuesta informa por fichero: `aceptados[]` y `rechazados[]` con
`nombre`, `code` y `detail`.

**Rationale**: FR-018 exige conservar los aceptados e informar de los rechazados. Enviar N
peticiones introduciria condicion de carrera sobre el limite por asiento (D10) y complicaria la
atomicidad. La lista de rechazos es lo que hace accionable el mensaje al usuario.

**Alternatives considered**: *N peticiones secuenciales*: rechazado. El estado parcial
resultante seria indistinguible de un fallo de red.

## D14. Anti-enumeracion y no cacheo de las descargas

**Decision**: una referencia de documento o de asiento que no pertenece a la empresa activa
devuelve 404 con el mismo mensaje que un recurso inexistente ("El documento no existe o
pertenece a otra empresa"), y toda respuesta de descarga incluye `Cache-Control: no-store`.

**Rationale**: FR-013 exige negar el acceso incluso conocida la referencia. Un 403 en lugar de un
404 confirmaria la existencia del recurso y permitiria enumerar el contenido de otra empresa.
`no-store` evita que un navegador o un proxy compartido conserve evidencia de otro tenant. Sigue
el patron ya establecido en `api/ngo/libros.py:79-100`.

**Alternatives considered**: *403 para cross-tenant*: rechazado por fuga de informacion.

## D15. Ordenacion determinista del listado

**Decision**: `ORDER BY created_at, id` en el listado del asiento y en el listado global.

**Rationale**: dos documentos con la misma marca de tiempo deben ordenarse igual en cada
peticion; `id` es UUID y actua como desempate estable. Sin desempate el listado puede reordenar
filas entre recargas y los enlaces del tipo "documento 3 de 5" dejan de corresponder.

**Alternatives considered**: *orden alfabetico por nombre*: rechazado. El nombre lo elige el
usuario y no expresa secuencia de alta.

## D16. PDFs cifrados y limite de paginas

**Decision**: un PDF protegido con contrasena se rechaza con `documento_protegido`, y un PDF con
mas de `documento_max_paginas` se rechaza con `documento_paginas_excedidas`.

**Rationale**: sin este criterio, el caso limite "PDF protegido con contrasena" de la spec
queda sin comportamiento definido, y un PDF de 5.000 paginas se acepta y satura el detalle del
asiento, contradiciendo el criterio de rendimiento de SC-008.

**Alternatives considered**: *aceptar y avisar*: rechazado. El usuario no puede abrir el
contenido, luego el documento no aporta evidencia.

## D17. Lista cerrada de tipos de documento

**Decision**: enum `documento_tipo` con seis valores: `factura`, `recibo`, `extracto`,
`justificante`, `contrato` y `otro`. El cliente no puede introducir valores fuera del conjunto.

**Rationale**: FR-005 enumeraba cuatro valores y anadia "u otro" sin definir, lo que abria una
clasificacion sin criterio para filtrar y hacia imposible un filtro fiable. `contrato` se anade
porque un apunte de arrendamiento o de prestacion de servicios se documenta con un contrato, no
con un recibo. Mantener el enum cerrado permite indexar y filtrar sin ambiguedad.

**Alternatives considered**: *cadena libre*: rechazado. El filtro por tipo (FR-017) deja de ser
fiable.

## D18. Limites de longitud de los campos de texto

**Decision**: `nombre_original VARCHAR(255)`, `descripcion VARCHAR(500)` y
`baja_motivo VARCHAR(500)`.

**Rationale**: el caso limite "longitud excesiva" de la spec no estaba cuantificado. Un nombre de
fichero puede llegar a 255 caracteres, y con acentos 255 caracteres pueden exceder el limite de
bytes, asi que ademas se valida en la capa de aplicacion antes de insertar y se devuelve
`documento_nombre_largo` en lugar de un error de integridad.

**Alternatives considered**: *texto sin limite*: rechazado. Acabaria en la cabecera HTTP de la
descarga y en los metadatos de exportacion.

## D19. Importe informativo con precision decimal

**Decision**: columna `importe_informativo NUMERIC(18,4) NULL`, expuesta como string de cuatro
decimales, validada con `Decimal` y nunca sumada ni trasladada al asiento.

**Rationale**: el supuesto de la spec lo contempla y la constitution prohibe `float` para
importes. Al ser informativo, un valor incoherente con el asiento es un dato erroneo del
usuario, no un descuadre: se acepta y la interfaz lo muestra como referencia.

**Alternatives considered**: *omitir la columna*: rechazado. La spec la contempla y es la via por
la que un usuario concilia a mano un escaneo que no puede leer.

## D20. Validacion en servicio, no en el endpoint

**Decision**: la lectura del fichero, la comprobacion de tamano y la validacion de contenido
viven en `services/documentos/validacion.py`, que recibe `bytes`; la capa de API solo lee el
`UploadFile` y delega.

**Rationale**: la validacion es logica de dominio y debe ser comprobable en tests unitarios sin
construir un `TestClient` ni una sesion. Ademas permite reutilizarla si en el futuro entra una
importacion masiva de ficheros (SPEC-005).

**Alternatives considered**: *validar en el endpoint*: rechazado. Mezcla transporte y dominio y
rompe el patron de `api/*` delega en `services/*` que sigue todo el repositorio.

## D21. Registro del router en la aplicacion

**Decision**: `from api.documentos import router as documentos_router` en
`backend/src/main.py`, registrado despues de `asientos_router` y de `importexport_router`.

**Rationale**: el prefijo `/api/v1/documentos` no colisiona con ninguna ruta existente, asi que
el orden es irrelevante para el funcionamiento; se documenta igualmente para que nadie lo mueva
por error. `api/routes_registry.py` recorre los routers incluidos y exige que toda ruta de
datos tenga guarda `require_permission`: las cinco rutas nuevas la llevan, y la prueba
`rutas_sin_permiso` sigue verde.

**Alternatives considered**: *excluir la ruta de descarga en `EXCLUSIONES_NO_BYPASS`*: rechazado.
La descarga es exactamente el caso que mas debe estar protegido.

## D22. Trazabilidad FR a diseno

| Requisito | Donde se resuelve |
|---|---|
| FR-001, FR-004 | `documento_asiento.journal_entry_id` mas FK compuesta a `journal_entry` |
| FR-002, FR-014 | D8, D16 |
| FR-003 | D10 (`documento_max_bytes`) |
| FR-005 | columnas de `data-model.md` |
| FR-006 | D6 |
| FR-007 | `GET /documentos/{id}/descarga` mas D12, D14 |
| FR-008 | `GET /documentos/asiento/{id}` devuelve `total` |
| FR-009 | D3 |
| FR-010 | regla de servicio: solo el estado DRAFT admite baja |
| FR-011 | D5 |
| FR-012 | baja logica mas D10 (`documento_plazo_conservacion_anos`) |
| FR-013 | FK compuesta, indices por `empresa_id` y D14 |
| FR-015 | la operacion no escribe en `journal_entry` ni en `journal_entry_line` |
| FR-016 | D4 (`acct:crear` y `acct:baja`) |
| FR-017, FR-019 | `GET /documentos` con filtros |
| FR-018 | D13 |
| FR-020 | D11 |

## Dependencias y riesgos

- **Nuevas dependencias**: `pillow>=10.0,<13.0` en el `requirements.txt` de la raiz. `pypdf` ya
  estaba declarada.
- **Migracion**: `021_adjuntos_asiento.sql`. El 018 ya lo ocupaba `018_cashflow.sql`
  (SPEC-027), de modo que la migracion va con el siguiente numero libre. Registrarla
  **al final** de `db/migrate.py:ORDEN_PREFERENTE` y de
  `tests/unit/test_migrations.py:ESPERADAS`, en el mismo orden, o falla
  `test_orden_por_dependencias`. Espejo de triggers en `db/triggers.py` y contrato PostgreSQL en
  `tests/integration/test_pg_schema.py`.
- **Sin cambios de RBAC, sin cambios en los `Settings` existentes y sin tocar SPEC-002**: el
  asiento no se modifica en ningun punto.
- **Riesgo residual**: la previsualizacion depende del visor nativo del navegador. Si un
  navegador no puede renderizar el PDF, la descarga sigue siendo la via soportada; es una
  degradacion aceptable, no un fallo funcional.
