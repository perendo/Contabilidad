# API Contracts: Maestro de Terceros (Clientes y Proveedores) (SPEC-008)

**Fecha**: 2026-09-16 | **Feature**: [../spec.md](../spec.md)

Estilo: REST bajo `/api/v1` (todos los endpoints exigen la cabecera de empresa activa derivada de sesión; la empresa activa se deriva exclusivamente de la sesión, nunca del path). Respuestas JSON; importes como strings decimales (p. ej. `"123.4500"`), nunca números de coma flotante.

**Nota de multi-tenancy**: la empresa activa se deriva exclusivamente de la sesión (token de Authorization). No se acepta `empresa_id` en el path ni en el body del request.

## Terceros

### POST `/api/v1/terceros`
Alta de tercero (cliente y/o proveedor). Asigna automáticamente las subcuentas 430/410 en el plan de la empresa.

- Body:
```json
{
  "nif": "B12345678",
  "razon_social": "ACME Servicios S.L.",
  "es_cliente": true,
  "es_proveedor": true,
  "direcciones": [{"tipo": "FISCAL", "direccion": "C/ Mayor 1", "cp": "28001", "ciudad": "Madrid", "provincia": "Madrid"}],
  "telefono": "912345678",
  "correo": "contacto@acme.es",
  "iban": "ES9121000418450200051332",
  "banco": "Banco de Madrid"
}
```
- **201**: `{ "id", "nif", "razon_social", "subcuentas": [{ "tipo": "CLIENTE", "cuenta_codigo": "43000001" }, { "tipo": "PROVEEDOR", "cuenta_codigo": "41000001" }], "activo": true }`
- **422**: `{ "detail": "NIF/CIF inválido" }` (formato), `{ "detail": "IBAN inválido" }`, `{ "detail": "Correo electrónico inválido" }`.
- **409**: `{ "detail": "Ya existe un tercero con NIF B12345678 en esta empresa" }`.

**Reglas**: NIF único por empresa; IBAN validado con MÓDULO 97; subcuentas creadas en la misma transacción ACID; auditoría del alta.

### GET `/api/v1/terceros`
Listado paginado de terceros con filtros (rol, active, texto de búsqueda).
- **200**: `{ "items": [{ "id", "nif", "razon_social", "es_cliente", "es_proveedor", "activo", "iban" }], "total" }`

### GET `/api/v1/terceros/{id}`
Ficha del tercero con histórico y saldo pendiente (derivado).
- **200**: `{ "id", "nif", "razon_social", "es_cliente", "es_proveedor", "iban", "banco", "activo", "subcuentas": [...], "saldo_pendiente": "1234.5000", "facturas": [...], "movimientos_asientos": [...], "vencimientos": [...] }`
- **404**: si no pertenece a la empresa activa.

**Reglas**: histórico y saldo derivados por agregación (asientos SPEC-002 con la subcuenta, facturas SPEC-007, vencimientos SPEC-011) en `Decimal`; jamás de otra empresa.

### PATCH `/api/v1/terceros/{id}`
Modificar datos del tercero (razón social, contactos, direcciones, IBAN/banco).
- Body: `{ "razon_social"? , "es_cliente"?, "es_proveedor"?, "telefono"?, "correo"?, "iban"?, "banco"? }`
- **200**: `{ "id", "razon_social", "iban" }`
- **422**: validaciones de formato (IBAN, correo).
- **409**: si el cambio de NIF/IBAN requiere permiso de administrador (tercero con movimientos) y no se autoriza (403).

**Reglas**: cualquier cambio del maestro se audita (actor, timestamp UTC, IP, acción, payload); cambio de NIF con movimientos requiere permiso de administrador (SPEC-003/015).

### PATCH `/api/v1/terceros/{id}/nif`
Cambio de NIF con trazabilidad.
- Body: `{ "nif": "B99999999", "justificacion": "Error de cierre de NIF", "permiso_admin": true }`
- **200**: `{ "id", "nif_anterior", "nif_nuevo" }`
- **409**: si el tercero tiene movimientos y `permiso_admin=false`.

### POST `/api/v1/terceros/{id}/retirar`
Retirada/inactivación del tercero.
- **200**: `{ "id", "activo": false }` (inactivación; histórico conservado).
- **409**: si se intenta borrado físico (`eliminar: true`) con movimientos → `{ "detail": "El tercero tiene movimientos: solo se puede inactivar" }`.

**Reglas**: borrado físico solo sin movimientos (facturas, asientos, vencimientos); con movimientos solo inactivación; todo auditado.

### DELETE `/api/v1/terceros/{id}`
Borrado físico — solo si el tercero no tiene movimientos.
- **204** si OK.
- **409**: `{ "detail": "El tercero tiene movimientos: solo se puede inactivar" }`.

## Condiciones de pronto pago (T-08/FR-009)

### POST `/api/v1/terceros/{id}/condiciones`
Crear condición de pronto pago vigente del tercero.
- Body: `{ "plazo_dias": 10, "porcentaje": "2.00", "vigente": true, "override_factura_id": null }`
- **201**: `{ "id", "plazo_dias": 10, "porcentaje": "2.00", "vigente": true }`
- **422**: `{ "detail": "El porcentaje debe estar entre 0 y 100" }` o `"plazo_dias debe ser > 0"`; 409 si ya existe una vigente para el tercero.

### GET `/api/v1/terceros/{id}/condiciones`
Listado de condiciones del tercero. **200**: `{ "items": [...] }`.

### PATCH `/api/v1/terceros/{id}/condiciones/{cond_id}`
Modificar/desactivar condición vigente. **200**: `{ "id", "vigente": false }`.

## Tratamiento de errores

- `401/403`: autenticación/permisos (SPEC-003) — incluye falta de permiso de administrador para cambio de NIF con movimientos.
- `404`: tercero inexistente en la empresa activa (nunca filtra datos de otra empresa).
- `409`: conflicto de estado (NIF duplicado, baja con movimientos, condición vigente existente).
- `422`: validación de negocio (formato NIF/CIF, IBAN, correo, porcentaje, plazo).
- Errores de importes siempre en precisión decimal; el backend es el único que valida reglas de negocio.