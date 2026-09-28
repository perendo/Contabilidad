# Data Model: Navegación y superficies (SPEC-031)

**Fecha**: 2026-09-27 | **Plan**: [plan.md](plan.md) | **Research**: [research.md](research.md)

Una sola entidad nueva. El resto de la feature son estructuras de lectura derivadas.

---

## 1. `favorito_usuario` (NUEVO)

Vincula un usuario, una empresa y un destino de navegación, con su posición en el
orden elegido. Es la única tabla que añade esta feature.

### Campos

| Columna | Tipo | Nulo | Notas |
|---|---|---|---|
| `id` | `UUID` | no | PK, `default=uuid4` (convención del repositorio) |
| `empresa_id` | `BIGINT` | no | constitution III: en clave e índices |
| `usuario_id` | `BIGINT` | no | FK a `users.id` (BIGINT en este modelo, no UUID) |
| `destino` | `VARCHAR(64)` | no | **clave del mapa de superficies**, no una ruta |
| `orden` | `INTEGER` | no | posición elegida por el usuario, 1..N |
| `created_at` | `TIMESTAMPTZ` | no | UTC, `server_default=now()` |
| `updated_at` | `TIMESTAMPTZ` | no | UTC, `server_default=now()` |

### Restricciones

- `UNIQUE (empresa_id, usuario_id, destino)`: un destino no se puede marcar dos veces.
  Sin este índice, dos marcas simultáneas desde dos pestañas crean duplicados y el rail
  muestra el mismo destino dos veces.
- `UNIQUE (empresa_id, id)`: convención de las 30 specs, necesaria para las FKs compuestas.
- `CHECK (orden >= 1)`: el orden empieza en 1, no en 0.
- `CHECK (length(destino) > 0)`: rechaza la cadena vacía, que colisionaría en el UNIQUE.
- `FK (empresa_id, usuario_id) -> user_companies (empresa_id, usuario_id)`: **el favorito
  solo puede existir si el usuario está vinculado a esa empresa**. Esta es la garantía de
  que los favoritos de la empresa A no se filtran a la B: no basta con filtrar en el
  servicio, el dato es inválido sin la vinculación.
- Índices: `(empresa_id, usuario_id, orden)` para leer el conjunto ordenado;
  `(empresa_id, destino)` para validar un destino sin cargar el conjunto.

### Sin trigger de inmutabilidad

Es la única entidad de la feature que admite `DELETE`, y con razón: desmarcar un favorito es
la baja de un marcado, no la pérdida de evidencia contable. No hay asiento, ni importe, ni
referencia a el. La trazabilidad de la marca queda en `audit_log` (constitution, sección de
stack: toda escritura se audita), no en la propia fila.

`audit_log` es append-only y triggers de `journal_entry` son WORM: nada de esto se solapa.

### Índices en SQLite

`user_companies` ya tiene clave compuesta `(empresa_id, usuario_id)` (SPEC-003), así que la
FK compuesta es viable en `create_all` de los tests, igual que en SPEC-030.

---

## 2. `ContextoSesion` (derivado, sin persistencia)

Respuesta de `GET /api/v1/contexto`. No es tabla: se calcula en cada petición a partir del
usuario autenticado y la empresa de la sesión.

```text
ContextoSesion
├── usuario:      { id, email, nombre, rol }
├── empresa:      { id, nombre, nif, es_activa }
├── ejercicios:   [ EjercicioResuelto ]   (todos los de la empresa, para el selector)
└── ejercicio_activo: EjercicioResuelto
```

### `EjercicioResuelto`

| Campo | Tipo | Origen | Notas |
|---|---|---|---|
| `ejercicio` | `int` | `EjercicioContable.ejercicio` | año contable |
| `estado` | `enum` | **derivado** | research D4, ver abajo |
| `es_actual` | `bool` | derivado | `ejercicio == año en curso` |
| `n_asientos` | `int` | `COUNT` sobre `journal_entry` | FR-017 |
| `es_seleccionable` | `bool` | derivado | `false` si el ejercicio no existe en ninguna fuente |

### Estados derivados (research D4)

```text
cerrado       si EjercicioContable.estado == 'cerrado'
             o FiscalYear.is_closed == true          (más restrictivo gana)
con_apertura  si EjercicioContable.estado == 'con_apertura' y no cerrado
abierto       en cualquier otro caso
```

`FiscalYear` inexistente se trata como abierto, que es la convención ya establecida en
SPEC-004 ("año inexistente = abierto"). El estado derivado gobierna **a la vez** lo que se
muestra y lo que se puede escribir, de modo que la información y la posibilidad de escribir no
pueden discrepar (FR-019).

### `n_asientos`: el filtro que no se puede olvidar

```sql
SELECT COUNT(*) FROM journal_entry
 WHERE empresa_id = :empresa_de_la_sesion
   AND ejercicio = :ejercicio
   AND estado    = 'POSTED'
```

**Correccion (2026-09-27, implementacion de US1).** La primera version de este
documento contaba por rango de fechas. Al implementar se comprobo que
`journal_entry` **ya tiene columna `ejercicio`**: es NOT NULL, la rellena el motor
de SPEC-002 con `fecha.year`, y forma parte de la restriccion
`uq_journal_entry_tenant_numero (empresa_id, ejercicio, numero_asiento)`.

Eso obliga a contar por la columna, y es mejor por dos razones: es el valor
**autoritativo guardado en el asiento** en vez de deducido de la fecha, y el filtro
aprovecha el indice unico, que ya tiene `(empresa_id, ejercicio)` como prefijo. Con
rango de fechas habria que volver a deducir el ejercicio y una empresa con
ejercicio desplazado contaria mal.

Dos corolarios:

1. `EXTRACT(YEAR FROM fecha)` queda descartado por partida doble: no existe en
   SQLite y ninguna funcion sobre la columna puede aprovechar un indice.
2. **La migracion `023_indice_contexto.sql` se cancela**: el indice que hacia falta
   ya existe como prefijo del unico.

Los dos límites salen de `EjercicioContable` (`inicio` y `fin`), nunca se calculan con una
función de fecha. Es la decisión que hay que tomar: `EXTRACT(YEAR FROM fecha)` es
**PostgreSQL puro y no existe en SQLite**, que es el motor de la suite de tests, y además
ninguna función sobre la columna puede aprovechar un índice. La comparación de rango de
fechas sí lo aprovecha, y es el patrón que ya usa el repo tras SPEC-029.

`empresa_id` **siempre** primero, siempre de la sesión. Es el Principio V(b) de esta
feature: la prueba de aislamiento cross-empresa comprueba que `n_asientos` de la empresa A no
incluye asientos de la B aunque ambas tengan el mismo ejercicio.

**Índice que lo sostiene**: ninguno nuevo. `uq_journal_entry_tenant_numero
(empresa_id, ejercicio, numero_asiento)` ya cubre el filtro, y el recuento filtra por
igualdad en sus dos primeras columnas.

---

## 3. Mapa de superficies (frontend, fuente única)

`frontend/src/components/navigation/surfaces.ts` es la **única** fuente de verdad de qué
pantalla pertenece a qué superficie. El guard de mapa la consume, de modo que una pantalla
nueva sin asignar rompe la suite en vez de quedar huérfana.

```text
Superficie
├── clave:        'contabilidad' | 'facturacion' | 'tesoreria'
│                 | 'informes' | 'fiscal' | 'maestros'
├── etiqueta:     'Contabilidad' ...   (corta; M3: no recortar, acortar)
├── icono:        nombre del icono
├── landing:      '/contabilidad' ... (existe o se crea)
├── permiso:      ('acct', 'ver')   por defecto, sobrescribible por destino
└── destinos:     [ Destino ]

Destino
├── clave:        'asientos'   (estable; es lo que se guarda en favorito_usuario)
├── etiqueta:     'Asientos'
├── ruta:         '/asientos/diario'   (puede cambiar sin romper favoritos)
├── permiso:      ('acct', 'ver')
├── grupo:        etiqueta de grupo dentro de la superficie, opcional
└── accion:       bool — si es acción, no aparece en navegación (FR-013)
```

`clave` y `ruta` separadas es lo que hace cumplir FR-026: reubicar una opción cambia `ruta` y
deja `clave` intacta, así que los favoritos siguen resolviendo.

---

## 4. Estados de la interfaz y su clase

Cuatro estados de ejercicio, cada uno con **color + etiqueta de texto**, nunca color solo
(research D7, CHK030):

| Estado | Color | Etiqueta | `es_seleccionable` |
|---|---|---|---|
| `abierto`, `es_actual` | neutro | (ninguna) | sí |
| `abierto`, no actual | ambar | `cerrando` | sí |
| `con_apertura` | neutro | `apertura` | sí |
| `cerrado` | rojo | `cerrado` | no |
| inexistente | gris | — | no |

La etiqueta de texto es lo que hace el estado legible sin color y lo que evita que
CHK030 quede abierto.

---

## 5. Lo que NO se modela

| Elemento | Por qué no |
|---|---|
| Contador de uso de destino | Se descartó automatizar la orden de favoritos (decisión del usuario: marcado manual). Sin contador, no hay entidad. |
| Preferencia de ejercicio activa persistida | Vive en cliente, indexada por `(empresa, ejercicio)`. Persistirla en servidor exigiría una tabla por usuario para un valor que el cliente ya conoce y que la cabecera transporta. |
| Historial de cambios de favoritos | Vive en `audit_log`, que ya es append-only y obligatorio por la constitution. Una tabla propia duplicaría la auditoría. |
| Estado de navegación por ruta | El rail se deriva de la ruta activa; no hay estado que persistir. |
| Permiso por destino nuevo | No hay módulo RBAC nuevo (research D10). |
