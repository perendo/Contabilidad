# API Contracts: Plantillas de Asientos (SPEC-018)

**Branch**: `018-plantillas-asientos` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Convención empresa activa**: el `empresa_id` NUNCA viaja en la ruta ni en el body; se deriva exclusivamente de la cabecera/contexto de sesión autenticada (`X-Empresa-Activa`). Toda mutación/lectura filtra por ese `empresa_id`.

Prefix general: `/api/v1` (router `templates`).

## REST

| Método | Ruta | Función | Body / Respuesta | Errores |
|---|---|---|---|---|
| `POST` | `/api/v1/plantillas` | Crear plantilla | Body: `{nombre, descripcion?, categoria?, lineas:[{orden, cuenta_id, posicion, importe_fijo?}, ...], variables:[{nombre, es_requerida?}], }` · Resp 201: `PlantillaDTO` con `id` y `version_actual=1` | 401 no autenticado; 403 sin permiso (SPEC-015); 409 nombre duplicado; 422 cuenta inexistente en el plan / línea fija y variable a la vez / variable no declarada |
| `GET` | `/api/v1/plantillas` | Listar plantillas de la empresa (paginado) | Query: `estado|categoria|q` · Resp 200: `Pagina<PlantillaDTO>` | 401; 403 |
| `GET` | `/api/v1/plantillas/{id}` | Detalle con líneas y variables | Resp 200: `PlantillaDetalleDTO` | 401; 403; 404 no existe o de otra empresa |
| `PATCH` | `/api/v1/plantillas/{id}` | Editar plantilla (incrementa `version_actual`) | Body parcial: nombre/descripcion/categoria/lineas/variables · Resp 200 | 401; 403; 404; 409 nombre duplicado; 422 cuenta inválida / variable referenciada eliminada |
| `POST` | `/api/v1/plantillas/{id}/activar` | Activar | Resp 200 | 401; 403; 404; 409 ya activa |
| `POST` | `/api/v1/plantillas/{id}/inactivar` | Desactivar (bloquea generación; no borra) | Resp 200 | 401; 403; 404; 409 ya inactiva |
| `POST` | `/api/v1/plantillas/{id}/generar` | Generar asiento desde plantilla | Body: `{fecha_asiento DATE, variables: {var_id: Decimal-string}, concepto?}` · Resp 201: `AsientoGeneradoDTO` (asiento_id, numero, lines resueltas, Debe/Haber) | 401; 403; 404 plantilla inexistente/otra empresa; 409 plantilla inactiva / ejercicio cerrado / plantilla no cuadra (Sum debe != Sum haber); 422 variable faltante o no numérica |
| `GET` | `/api/v1/plantillas/{id}/generados` | Listar asientos generados de una plantilla | Resp 200: `Pagina<AsientoGeneradoDTO>` (incluye `version_plantilla` y fecha) | 401; 403; 404 |

### Notas de código

- **422 vs 409**: 422 para datos inválidos (faltan variables, cuenta no existe, expresión no numérica); 409 para conflictos de estado/negocio (inactiva, ejercicio cerrado, plantilla no cuadra).
- **403 vs 404**: 403 permisos (SPEC-015); 404 inexistencia real o cross-tenant (no revelar existencia).
- La generación devuelve el asiento **ya posteado** (201) o, si el motor soporta borrador explícito, el borrador persistido; la validación de balance y ejercicio siempre ocurre en el backend (constitución I).
- Numero correlativo: el `numero` del asiento generado lo asigna el motor (SPEC-002) por (empresa, ejercicio) con secuencia bloqueada en la misma transacción.
- Variables en `variables_aportadas` se serializan como `Decimal` string (nunca float).

## Ficheros de formato externo

No aplica (SPEC-018 no intercambia ficheros normalizados con terceros).