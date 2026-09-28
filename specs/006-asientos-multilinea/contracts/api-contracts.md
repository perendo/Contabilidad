# API Contracts: Asientos Contables Multilínea (SPEC-006)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Estilo: REST bajo `/api/v1` (todos los endpoints exigen la cabecera de empresa activa derivada de sesión; la empresa activa se deriva exclusivamente de la sesión, nunca del path). Respuestas JSON; importes como strings decimales (p. ej. `"123.4500"`), nunca números de coma flotante.

**Nota de multi-tenancy**: la empresa activa se deriva exclusivamente de la sesión (token de Authorization). No se acepta `empresa_id` en el path ni en el body del request.

## Crear asiento multilínea

### POST `/api/v1/asientos`

Crear un asiento con N partidas al Debe y M partidas al Haber (o el caso clásico 1:1).

- Body:
```json
{
  "fecha": "2026-01-15",
  "concepto": "Gasto parcialmente deducible",
  "lineas": [
    { "cuenta": "6200000", "debe": "500.0000", "haber": "0.0000", "detalle": "Gasto deducible" },
    { "cuenta": "6210000", "debe": "200.0000", "haber": "0.0000", "detalle": "Gasto no deducible" },
    { "cuenta": "4100000", "debe": "0.0000", "haber": "700.0000", "detalle": "Proveedor" }
  ]
}
```
- **201**: `{ "id", "numero_asiento", "fecha", "concepto", "total_debe": "700.0000", "total_haber": "700.0000", "n_lineas": 3, "estado": "POSTED" }`
- **422**: errores de validación:
  - `lado_vacio`: "Faltan partidas en el lado HABER" o "DEBE".
  - `desbalanceo`: "Suma Debe (700.0000) != Suma Haber (650.0000)".
  - `linea_invalida`: "Línea con debe y haber ambos > 0" o "Línea con debe y haber ambos = 0".
  - `cuenta_no_encontrada`: "Cuenta 9990000 no encontrada en el plan".
  - `cuenta_no_apuntable`: "Cuenta 1000000 no es apuntable".
  - `ejercicio_cerrado`: "La fecha 2025-01-15 pertenece a un ejercicio cerrado".
  - `limite_lineas_excedido`: "Máximo 100 líneas por asiento".

**Reglas**: re-validación completa en backend; `Decimal` para todos los importes; transacción atómica (cabecera + líneas); numeración correlativa por (empresa_id, ejercicio) con `SELECT ... FOR UPDATE`.

## Anular asiento multilínea

### POST `/api/v1/asientos/{id}/anular`

Generar asiento rectificativo con todas las líneas invertidas.

- **201**: `{ "asiento_rectificativo": { "id", "numero_asiento", "tipo": "REVERSAL", "total_debe", "total_haber", "n_lineas" }, "asiento_original_id" }`
- **409**: si el asiento original no está `POSTED`.
- **404**: si el asiento no pertenece a la empresa activa.

**Reglas**: se genera un nuevo JournalEntry con tipo `REVERSAL`; cada línea original se invierte (Debe↔Haber); el resultado cuadra (inversión exacta); el original no se modifica; todo en transacción ACID con audit log.

## Consultar asiento con sus líneas

### GET `/api/v1/asientos/{id}`

Detalle de un asiento con todas sus líneas (para ver la estructura multilínea).

- **200**: `{ "id", "numero_asiento", "fecha", "concepto", "estado", "tipo", "asiento_original_id", "lineas": [{ "id", "cuenta", "debe", "haber", "detalle" }], "total_debe", "total_haber" }`
- **404**: si no pertenece a la empresa activa.

## Listar asientos

### GET `/api/v1/asientos`

Listado de asientos con filtros de fecha y paginación. Cada asiento muestra su resumen de líneas.

- Query params: `fecha_desde`, `fecha_hasta`, `estado`, `page`, `page_size`.
- **200**: `{ "items": [{ "id", "numero_asiento", "fecha", "concepto", "estado", "total_debe", "total_haber", "n_lineas" }], "total" }`

## Tratamiento de errores

- `401/403`: autenticación/permisos (SPEC-003).
- `404`: recurso inexistente en la empresa activa (nunca filtra datos de otra empresa).
- `409`: conflicto de estado (asiento no POSTED para anular, ejercicio cerrado).
- `422`: validación de negocio (desbalanceo, lado vacío, líneas inválidas, cuentas, límite de líneas).
- Errores de importes siempre en precisión decimal; el backend es el único que valida partida doble.
