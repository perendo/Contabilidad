# API Contracts: Navegación y superficies (SPEC-031)

**Fecha**: 2026-09-27 | **Plan**: [plan.md](plan.md) | **Research**: [research.md](research.md)

Convenciones heredadas y obligatorias del repositorio:

- Prefijo `/api/v1/...` en todos los endpoints.
- `empresa_id` **nunca** en path ni en body. Se deriva de la sesión vía
  `Depends(get_empresa_id)`. Un `rg "/api/\{.*empresa"` no debe dar coincidencias.
- Errores con cuerpo `{"code": "...", "detail": "..."}` y código HTTP coherente.
- `router` registrado en `main.py`; con guard `require_permission` para que
  `api.routes_registry.rutas_sin_permiso` siga en **0**.

---

## 1. Cabecera `X-Ejercicio-Activa`

**Nueva.** Paralela a `X-Empresa-Activa`, con la misma política de confianza: llega del
cliente, es no confiable, y el servidor la valida.

| Aspecto | Valor |
|---|---|
| Nombre | `X-Ejercicio-Activa` |
| Formato | entero de 4 dígitos, `1900`-`2999` |
| Obligatoria | no; si falta, se usa el año en curso |
| Ámbito | filtro **dentro** de la empresa activa, no frontera de tenant |
| Precedencia | un `?ejercicio=` explícito en la URL **gana** a la cabecera |
| Validación | el ejercicio MUST pertenecer a la empresa activa de la sesión |

```http
GET /api/v1/asientos?empresa=&ejercicio=
X-Empresa-Activa: 10
X-Ejercicio-Activa: 2025
Authorization: Bearer <token>
```

Respuesta 422 si el ejercicio no pertenece a la empresa activa:

```json
{"code": "ejercicio_no_pertenece_a_empresa", "detail": "El ejercicio 2025 no pertenece a la empresa activa."}
```

**Por qué no viola la constitution III**: el principio exige que `empresa_id` se derive del
contexto autenticado y nunca de datos del cliente. El ejercicio no es `empresa_id` ni sustituye
al filtro de empresa: se aplica **después** de resolver la empresa, y MUST validar contra
ella. Un ejercicio de la empresa B no se resuelve nunca en el contexto de la A.

---

## 2. `GET /api/v1/contexto` (NUEVO)

Devuelve todo lo que el shell necesita en **una** llamada: identidad, empresa, ejercicios y
ejercicio activo. Antes, el shell solo tenía los dos selectores sueltos y ninguna lectura
compartida.

**Guard**: `require_permission("acct", "ver")` — los tres roles base lo poseen, así que
cualquier usuario con acceso a la contabilidad puede pintar el shell (FR-006, redactado como
propiedad y no como nombre de permiso).

### 200 (respuesta)

```json
{
  "usuario": {"id": 7, "email": "jperez@empresa.es", "nombre": "J. Pérez", "rol": "ACCOUNTANT"},
  "empresa": {"id": 10, "nombre": "Diez SL", "nif": "B00000010", "es_activa": true},
  "ejercicio_activo": {
    "ejercicio": 2026,
    "estado": "abierto",
    "es_actual": true,
    "n_asientos": 37,
    "es_seleccionable": true
  },
  "ejercicios": [
    {"ejercicio": 2025, "estado": "abierto",   "es_actual": false, "n_asientos": 1842, "es_seleccionable": true},
    {"ejercicio": 2026, "estado": "abierto",   "es_actual": true,  "n_asientos": 37,   "es_seleccionable": true},
    {"ejercicio": 2027, "estado": "cerrado",   "es_actual": false, "n_asientos": 0,    "es_seleccionable": false}
  ]
}
```

`estado` ∈ `abierto` | `con_apertura` | `cerrado`, derivado según research D4 (más
restrictivo gana). `es_seleccionable` es `false` para ejercicios cerrados o inexistentes.

### Errores

| Código | HTTP | Cuándo |
|---|---|---|
| (401 del guard) | 401 | sin sesión |
| (403 del guard) | 403 | usuario sin `acct:ver` en la empresa activa |
| (404 del guard) | 404 | `X-Empresa-Activa` que no pertenece al usuario |
| `ejercicio_no_pertenece_a_empresa` | 422 | `X-Ejercicio-Activa` de otra empresa |

**Garantía de aislamiento**: `n_asientos` se cuenta con `empresa_id` de la sesión **y**
`estado = 'POSTED'`. Los ejercicios devueltos son los de esa empresa, nunca los de otra. Es el
Principio V(b) de esta feature y tiene prueba dedicada
(`test_contexto_tenant_isolation.py`).

**Nota de rendimiento**: el presupuesto vive en el plan (p95 < 300 ms) y lo mide `T069`
contra `SC-013`. El recuento filtra por `empresa_id`, `ejercicio` y `estado`, sobre el indice
`uq_journal_entry_tenant_numero (empresa_id, ejercicio, numero_asiento)`, que ya existe en
`003_journal.sql` y cubre el filtro por igualdad en sus dos primeras columnas. **No hace falta
ningún índice nuevo**, y por eso se canceló la migración `023_indice_contexto.sql`.

---

## 3. Favoritos

### `GET /api/v1/favoritos`

Guard `require_permission("acct", "ver")`. Devuelve los favoritos del usuario en la empresa
activa, **incluidos los que ya no puede abrir** (van marcados, no filtrados: FR-024 exige
conservarlos).

```json
{
  "items": [
    {"destino": "vencimientos", "orden": 1, "accesible": true},
    {"destino": "conciliacion", "orden": 2, "accesible": false}
  ],
  "total": 7,
  "visibles": 5
}
```

`total` es el número de favoritos guardados; `visibles` es el número que el cliente
muestra, que es como máximo 5. Cuando `total > visibles`, el cliente MUST avisar de
que hay favoritos ocultos, y el orden de los ocultos MUST conservarse para que
reaparezcan si el usuario desmarca otro.

`accesible: false` significa que el destino existe en el mapa de superficies pero el usuario
no tiene el permiso. El cliente lo oculta y **no lo borra**.

Destino inexistente en el mapa (se reubicó y cambió la clave) → `accesible: false` y
`desconocido: true`, para que la interfaz pueda ofrecer retirarlo sin perder la fila.

### `PUT /api/v1/favoritos/{destino}`

Guard `require_permission("acct", "editar")`. Marca como favorito. Idempotente.

```json
{"destino": "vencimientos", "orden": 1}
```

- `destino` MUST existir en el mapa de superficies → si no, **404**
  `destino_desconocido`. Esto es lo que hace que la clave estable (FR-026) valga: la ruta
  puede haber cambiado, la clave no.
- `orden` MUST ser un entero positivo → si no, **422** `orden_fuera_de_rango`. Este 422
  concierne al **valor de la posición**, no a la cantidad de favoritos: un `orden` de 9
  es inválido aunque el conjunto esté vacío.
- **Superar el máximo de 5 NO es un error.** Un sexto favorito se **guarda** y la
  respuesta es **201**; el recorte a 5 ocurre en la lectura (`GET`), que ordena por
  `orden`, devuelve los primeros 5 e informa `total`. FR-025 limita los favoritos
  *visibles*, y el caso borde del spec exige que el que no se muestra no se pierda.
  Rechazar aquí con 422 dejaría al usuario con 5 favoritos sin poder añadir el suyo.
- Si ya está marcado, **200** con el mismo cuerpo (idempotente, no 409): marcar dos veces el
  mismo destino desde dos pestañas es un gesto normal del usuario, no un error.
- **Auditoría obligatoria**: `FAVORITO_MARCAR` con usuario, IP, UTC y payload, en la misma
  transacción ACID (constitution, sección de stack).

### `DELETE /api/v1/favoritos/{destino}`

Guard `require_permission("acct", "editar")`. Desmarca. Idempotente: si no estaba, **204**.

- **Auditoría obligatoria**: `FAVORITO_DESMARCAR`, misma regla.
- El borrado es físico: es la única entidad de la feature que se borra, y desmarcar no
  destruye evidencia contable (data-model §1).

### `PATCH /api/v1/favoritos` (reordenar)

Guard `require_permission("acct", "editar")`. Fija el orden completo del conjunto.

```json
{"ordenes": ["vencimientos", "conciliacion", "asientos"]}
```

MUST contener exactamente el conjunto actual, sin repeticiones y sin omitir ninguno →
**422** `conjunto_incompleto` si no cuadra. Es deliberado: un reordenamiento parcial
deja el conjunto en un estado que el usuario no pidió y que no sabe reproducir.

---

## 4. Endpoints que **no** se crean

| No se crea | Por qué |
|---|---|
| Listar empresas | Ya existe `GET /api/v1/companies` (SPEC-003). La lista de la superficie Maestros lo consume. |
| Listar ejercicios | Ya existe `GET /api/v1/fiscal-years`. `GET /api/v1/contexto` lo **absorbe** y añade el estado derivado y los contadores, de modo que el shell hace una llamada y no dos. |
| Mover o renombrar superficies | El mapa de superficies es frontend y se despliega con la aplicación. No hay nada que mutar en el servidor. |
| Cualquier escritura contable | Esta feature no toca el motor de asientos. |

---

## 5. Cambios de contrato en el cliente

`frontend/src/services/client.ts` añade `X-Ejercicio-Activa` a toda petición, con la misma
política que ya aplica a `X-Empresa-Activa`. Si una pantalla pide `?ejercicio=2025` de forma
explícita, el parámetro gana y la cabecera acompaña sin sobreescribirlo (research D3).

**Login** escribe el token en cookie HTTP-only (para el `middleware.ts`) **y** en
`localStorage` (para el encabezado `Authorization` existente). `logout` limpia ambos.

**El `middleware.ts` no es un control de seguridad.** Comprueba presencia de cookie y redirige;
la verificación real es el 401 del backend, que ya funciona. Ver research D2 y CHK040.
