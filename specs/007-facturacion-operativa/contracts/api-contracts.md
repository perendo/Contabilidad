# API Contracts: Facturación Operativa (SPEC-007)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Estilo: REST bajo `/api/v1` (todos los endpoints exigen la cabecera de empresa activa derivada de sesión; la empresa activa se deriva exclusivamente de la sesión, nunca del path). Respuestas JSON; importes como strings decimales (p. ej. `"123.4500"`), nunca números de coma flotante.

**Nota de multi-tenancy**: la empresa activa se deriva exclusivamente de la sesión (token de Authorization). No se acepta `empresa_id` en el path ni en el body del request.

## Series de facturación

### POST `/api/v1/facturacion/series`
Crear serie de facturación.
- Body: `{ "codigo": "FV", "nombre": "Facturas de venta", "prefijo": "FV", "sufijo": "" }`
- 201: `{ "id", "codigo", "prefijo", "estado": "activa" }`
- 409: `{ "detail": "Serie FV ya existe" }`.

### GET `/api/v1/facturacion/series`
Listado de series de la empresa activa. 200: `{ "items": [...] }`.

## Facturas

### POST `/api/v1/facturacion/facturas`
Crear factura en borrador (sin número ni asiento). Para ventas usa la cuenta 430 del tercero; para compras 410.

- Body:
```json
{
  "serie_id": "<uuid>",
  "ejercicio": 2026,
  "fecha": "2026-01-20",
  "tipo": "VENTA",
  "tercero_id": "<uuid-cliente>",
  "concepto_global": "Venta de material",
  "lineas": [
    { "descripcion": "Material A", "cantidad": "2.0000", "precio_unitario": "250.0000", "porcentaje_descuento": "0.0000", "tipo_iva": "21.00", "tipo_recargo": "0.00", "tipo_irpf": "0.00", "base_irpf": "0.0000" },
    { "descripcion": "Material B", "cantidad": "1.0000", "precio_unitario": "100.0000", "porcentaje_descuento": "5.00", "tipo_iva": "21.00", "tipo_recargo": "0.00", "tipo_irpf": "0.00", "base_irpf": "0.0000" }
  ]
}
```
- 201: `{ "id", "estado": "borrador", "serie_id", "numero": null, "asiento_id": null, "importe_total": "0.0000" }`
- 422: validación de líneas (cantidad/precio/descuento/tipos), tercero inexistente.

### POST `/api/v1/facturacion/facturas/{id}/emitir`
Confirmar la factura: asigna número correlativo, genera el asiento vinculado (espec 002/006) y pasa a `emitida`.

- 200: `{ "id", "numero": "FV1", "estado": "emitida", "importe_base", "importe_iva", "importe_recargo", "importe_irpf", "importe_total", "asiento_id", "asiento_numero" }`
- 400: `{ "detail": "La fecha 2025-12-20 pertenece a un ejercicio cerrado" }`.
- 409: si ya está emitida.

**Reglas**: cálculo de impuestos en `Decimal` (redondeo línea a línea); asíгnv vinculado balanceado; numeración atómica por (empresa_id, serie_id, ejercicio) con `SELECT ... FOR UPDATE`.

### GET `/api/v1/facturacion/facturas`
Listado de facturas con filtros (`serie_id`, `estado`, `fecha_desde`, `fecha_hasta`, `ejercicio`), paginación.
- 200: `{ "items": [{ "id", "numero", "fecha", "tipo", "tercero_id", "importe_total", "estado", "asiento_id" }], "total" }`.

### GET `/api/v1/facturacion/facturas/{id}`
Detalle de factura con sus líneas y el asiento vinculado.
- 404: si no pertenece a la empresa activa.

### DELETE `/api/v1/facturacion/facturas/{id}`
Eliminar factura **solo en borrador**. 204 si OK; 409 si está emitida/anulada.

### POST `/api/v1/facturacion/facturas/{id}/rectificar`
Generar factura rectificativa (abono). Crea una `RECTIFICATIVA` con líneas invertidas y genera asiento `REVERSAL` enlazado, sin tocar el asiento original.

- Body: `{ "serie_id": "<uuid>", "motivo": "Error en factura" }` (opcionalmente `lineas` para rectificación parcial; por defecto invierte todas).
- 201: `{ "factura_rectificativa_id", "numero", "asiento_reversal_id", "importe_total" }`
- 409: si la factura original está `borrador` o `anulada`; 404 si no existe en la empresa activa.

### POST `/api/v1/facturacion/facturas/{id}/anular`
Marcar una factura emitida como `anulada` (por rectificativa total). 200 si OK; 409 si no está `emitida`.

## Recargo de equivalencia y criterio de caja

- El **recargo de equivalencia** (FR-010) se configura por empresa/cuenta (SPEC-001); al emitir, las líneas calculan `cuota_recargo` y el total se contabiliza en cuenta separada del IVA (477/472 recargo). Opcionalmente se puede indicar `tipo_recargo` por línea.
- El **criterio de caja** (FR-011) se configura por empresa; al emitir, la factura lleva `regimen_caja: true` y `iva_devengado: false`. El IVA íntegro queda en 477/472 con saldo pendiente; SPEC-012 gestiona la liquidación al cobro/pago. El endpoint devuelve ambos campos en el detalle.

## Tratamiento de errores

- `401/403`: autenticación/permisos (SPEC-003).
- `404`: recurso inexistente en la empresa activa (nunca filtra datos de otra empresa).
- `400/409`: conflicto de estado (ejercicio cerrado, factura ya emitida, baja de emitida, serie duplicada).
- `422`: validación de negocio (líneas, importes, impuestos, tercero).
- Errores de importes siempre en precisión decimal; el backend es el único que valida partida doble.