# API Contracts: Documentos adjuntos al asiento (SPEC-030)

**Feature**: `specs/030-documentos-asiento/spec.md` · **Date**: 2026-09-26
**Router**: `backend/src/api/documentos.py` · **Prefijo**: `/api/v1/documentos`

Prefijo plano con segmento estatico `/asiento/{asiento_id}` para no colisionar con la ruta
comodin `GET /api/v1/asientos/{entry_id}` de SPEC-002 y SPEC-006 (research.md D7).

---

## 0. Convenciones comunes

### Autenticacion y contexto de empresa

Todas las rutas requieren:

| Cabecera | Valor | Origen |
|---|---|---|
| `Authorization` | `Bearer <JWT>` | Sesion del usuario; 401 si falta o es invalido |
| `X-Empresa-Activa` | `<empresa_id>` | Contexto de empresa; 403 si falta, no es entero positivo, el usuario no tiene `UserCompany` activa, o la empresa esta inactiva |

`empresa_id` **nunca** se acepta en el cuerpo, en la query ni en la ruta. Se deriva de
`Depends(get_empresa_id)` (constitution III).

### Permisos

Se reutiliza el modulo RBAC `acct` ya existente (research.md D4).

| Operacion | Guard | Efecto |
|---|---|---|
| Listar, consultar metadatos, previsualizar y descargar | `require_permission("acct", "ver")` | 403 `sin_permiso` |
| Adjuntar | `require_permission("acct", "crear")` | 403 `sin_permiso` |
| Dar de baja | `require_permission("acct", "baja")` | 403 `sin_permiso` |

El acceso denegado se audita antes de responder 403, dentro de la misma transaccion.

### Formato de error

```json
{
  "detail": {
    "code": "documento_duplicado",
    "detail": "Ya existe un documento con esa huella en este asiento"
  }
}
```

En la carga multiple, `detail` se sustituye por el desglose por fichero descrito en el
contrato 1.

### Anti-enumeracion

Un recurso que no pertenece a la empresa activa devuelve **404** con el mismo texto que un
recurso inexistente. No se distingue "no existe" de "es de otra empresa" (research.md D14).

---

## 1. `POST /api/v1/documentos/asiento/{asiento_id}`

Adjunta uno o varios documentos a un asiento. Es la unica operacion de escritura que anade
contenido.

**Guard**: `require_permission("acct", "crear")`
**Content-Type**: `multipart/form-data`

### Campos del formulario

| Campo | Tipo | Obligatorio | Notas |
|---|---|---|---|
| `files` | lista de ficheros | si | PDF o imagen. Varios ficheros en una sola peticion (research.md D13) |
| `tipo_documento` | texto | si | Uno de `factura`, `recibo`, `extracto`, `justificante`, `contrato`, `otro` |
| `descripcion` | texto | no | Maximo 500 caracteres |
| `importe_informativo` | texto | no | Decimal con 4 decimales. String, nunca float. Referencia visual: no altera el asiento |

### Respuesta 201

```json
{
  "aceptados": [
    {
      "id": "3f1c8a52-9d4e-4a1b-8c77-2e6b1a9d0f31",
      "asiento_id": "7b2d4e10-5c3f-4a91-b6d8-0e1f2a3b4c5d",
      "nombre_original": "factura-2026-0042.pdf",
      "extension": "pdf",
      "content_type": "application/pdf",
      "size_bytes": 248193,
      "num_paginas": 3,
      "sha256": "9f2b...c41a",
      "tipo_documento": "factura",
      "descripcion": "Factura del proveedor, pagina 1 de 3",
      "importe_informativo": "1210.0000",
      "estado": "activo",
      "created_by": "Contable Principal",
      "created_at": "2026-09-26T10:14:03.221Z"
    }
  ],
  "rechazados": [
    {
      "nombre": "captura.png.bak",
      "code": "formato_no_admitido",
      "detail": "Solo se admiten PDF, JPEG, PNG y TIFF"
    },
    {
      "nombre": "escaneo.tif",
      "code": "documento_demasiado_grande",
      "detail": "El documento supera el tamano maximo de 10 MB"
    }
  ]
}
```

**Codigos de respuesta**

| Codigo | Cuando |
|---|---|
| 201 | Siempre que la ruta sea valida, aunque `aceptados` este vacio: el detalle del rechazo va en el cuerpo, no en el codigo |
| 403 | Sin permiso `acct:crear`, o sin contexto de empresa valido |
| 404 | El asiento no existe o no pertenece a la empresa activa |
| 422 | Formulario invalido: `files` vacio, `tipo_documento` fuera del enum, `descripcion` o `importe_informativo` mal formados |

**Garantias**

- Los documentos aceptados se persisten en la misma transaccion que sus trazas de auditoria.
- El contenido nunca se reescribe: un `sha256` repetido en el mismo asiento produce
  `documento_duplicado` (409 en el detalle del rechazo) y no crea una segunda fila.
- No se toca `journal_entry` ni `journal_entry_line` (SC-007).
- Si un fichero de la lista falla, los demas se conservan (FR-018).
- Un asiento puede no tener nunca ningun documento: la ausencia no es un error.

---

## 2. `GET /api/v1/documentos/asiento/{asiento_id}`

Lista los documentos de un asiento, incluidos por defecto los dados de baja.

**Guard**: `require_permission("acct", "ver")`

### Query

| Parametro | Tipo | Def. | Notas |
|---|---|---|---|
| `incluir_bajas` | booleano | `true` | `false` devuelve solo los activos |

### Respuesta 200

```json
{
  "items": [ { "...": "mismo objeto que en el alta" } ],
  "total": 2,
  "documentos_obligatorios": false
}
```

**Codigos**: 200 · 403 · 404 (asiento de otra empresa o inexistente)

**Garantias**

- Devuelve `{"items": [], "total": 0, "documentos_obligatorios": false}` cuando el asiento no
  tiene ningun documento. Nunca 404 por falta de documentos (FR-020).
- `documentos_obligatorios` viaja siempre en `false`: expone explicitamente que la adjuncion es
  opcional, de modo que el cliente no pueda tratarla como un requisito pendiente.
- Orden estable `created_at, id` (research.md D15).

---

## 3. `GET /api/v1/documentos`

Listado global de los documentos de la empresa activa. Permite localizar una evidencia sin
conocer el numero de asiento (FR-019).

**Guard**: `require_permission("acct", "ver")`

### Query

| Parametro | Tipo | Def. | Notas |
|---|---|---|---|
| `asiento_id` | UUID | - | Filtra por asiento |
| `ejercicio` | entero | - | Filtra por el ejercicio del asiento, no por `created_at` |
| `tipo_documento` | texto | - | Valor del enum |
| `estado` | texto | - | `activo` o `dado_de_baja` |
| `q` | texto | - | Busca en `nombre_original` y `descripcion`, hasta 200 caracteres |
| `incluir_bajas` | booleano | `true` | `false` devuelve solo los activos |
| `page` | entero >= 1 | 1 | |
| `page_size` | entero 1..100 | 20 | |

El filtro por `ejercicio` se resuelve con un `JOIN` a `journal_entry`, porque el ejercicio es
una columna del asiento y no del documento: los documentos de un asiento de 2025 deben
aparecer al filtrar por 2025 aunque se adjuntaran mas tarde.

### Respuesta 200

```json
{
  "items": [ { "...": "mismo objeto que en el alta, mas journal_entry" } ],
  "total": 137,
  "page": 1,
  "page_size": 20
}
```

Cada item anade `journal_entry: { "id": "...", "numero": 42, "fecha": "2026-03-14", "ejercicio": 2026, "concepto": "..." }`.

**Codigos**: 200 · 403 · 422 (parametro de filtro invalido, `page_size` fuera de rango)

---

## 4. `GET /api/v1/documentos/{documento_id}`

Metadatos de un documento, sin el contenido binario.

**Guard**: `require_permission("acct", "ver")`
**Respuesta**: 200 con el objeto del documento, igual que en el alta · 403 · 404

---

## 5. `GET /api/v1/documentos/{documento_id}/descarga`

Devuelve el contenido integro del documento.

**Guard**: `require_permission("acct", "ver")`

### Respuesta 200

El binario, no JSON.

| Cabecera | Valor |
|---|---|
| `Content-Type` | `application/pdf`, `image/jpeg`, `image/png` o `image/tiff`, segun la firma detectada al dar de alta |
| `Content-Disposition` | `attachment; filename="<nombre_original>"` |
| `Cache-Control` | `no-store` |
| `X-Documento-SHA256` | La huella registrada en el alta, para que el cliente pueda verificarla sin recalcularla |

`nombre_original` se sanea antes de interpolarlo en la cabecera: se eliminan comillas dobles,
punto y coma, saltos de linea y demas caracteres no imprimibles, y se recorta a 255
caracteres, para que un nombre hostil no pueda inyectar cabeceras. Como una cabecera HTTP
solo admite ASCII, el nombre se emite en la doble forma de RFC 6266 (`filename` con un
equivalente ASCII y `filename*=UTF-8''...`), conservando intacto el original en la base de
datos y en los metadatos.

**Codigos**: 200 · 403 · 404

**Garantias**

- El contenido servido es byte a byte el del alta: su `sha256` coincide con
  `X-Documento-SHA256` (SC-002, SC-004).
- Un documento dado de baja **si** se puede descargar: el contenido se conserva durante el
  plazo legal (FR-012). Para ocultarlo se restringe el permiso `acct:ver`, no el almacenamiento.
- `Cache-Control: no-store` evita que un navegador o un proxy compartido retenga evidencia de
  otra empresa (research.md D14).
- El contenido nunca se expone en una URL publica: el frontend lo obtiene como `Blob`
  autenticado y lo muestra desde una URL de objeto local.

---

## 6. `DELETE /api/v1/documentos/{documento_id}`

Da de baja logica un documento. Solo es posible si su asiento esta en `DRAFT`.

**Guard**: `require_permission("acct", "baja")`
**Cuerpo**: `{"motivo": "Escaneo ilegible, se vuelve a subir"}` (obligatorio, max. 500 caracteres)

### Respuesta 204

Sin cuerpo. El documento pasa a `dado_de_baja` con su motivo, responsable y fecha; el contenido
y el `sha256` se conservan.

**Codigos**

| Codigo | `code` | Cuando |
|---|---|---|
| 204 | - | Baja realizada |
| 403 | `sin_permiso` | Sin permiso `acct:baja` |
| 404 | `documento_no_encontrado` | No existe, no es de la empresa activa, o ya esta dado de baja |
| 409 | `baja_no_permitida` | El asiento esta `POSTED` o `CANCELLED`: el soporte de un asiento asentado no se retira (FR-010) |
| 422 | `baja_motivo_obligatorio` | `motivo` vacio o de mas de 500 caracteres |

**Garantias**

- Idempotente por deteccion: un segundo `DELETE` sobre el mismo documento devuelve 404
  `documento_no_encontrado`, no 409.
- La baja se audita en la misma transaccion ACID que el `UPDATE` de estado (FR-011).
- No existe ninguna ruta de borrado fisico: el trigger `BEFORE DELETE` la rechazaria (FR-012).

---

## 7. Resumen de Superficie

| # | Metodo | Ruta | Guard | Escribe en el diario |
|---|---|---|---|---|
| 1 | POST | `/api/v1/documentos/asiento/{asiento_id}` | `acct:crear` | No |
| 2 | GET | `/api/v1/documentos/asiento/{asiento_id}` | `acct:ver` | No |
| 3 | GET | `/api/v1/documentos` | `acct:ver` | No |
| 4 | GET | `/api/v1/documentos/{documento_id}` | `acct:ver` | No |
| 5 | GET | `/api/v1/documentos/{documento_id}/descarga` | `acct:ver` | No |
| 6 | DELETE | `/api/v1/documentos/{documento_id}` | `acct:baja` | No |

Ninguna ruta escribe en `journal_entry` ni en `journal_entry_line`. Esa es la garantia
estructural de FR-015 y SC-007: adjuntar o dar de baja un documento no puede alterar el cuadre
del asiento ni su numero, fecha o estado contable.
