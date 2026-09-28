# API Contracts: Centros de Coste (SPEC-017)

**Branch**: `017-centros-de-coste` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Convención empresa activa**: el `empresa_id` NUNCA viaja en la ruta ni en el body; se deriva exclusivamente de la cabecera/contexto de sesión autenticada (`X-Empresa-Activa`). Toda mutación/lectura filtra por ese `empresa_id`.

Prefix general: `/api/v1` (los endpoints se registran bajo el router `costcenters`).

## REST

| Método | Ruta | Función | Body / Respuesta | Errores |
|---|---|---|---|---|
| `POST` | `/api/v1/centros` | Alta de centro de coste | Body: `{codigo, nombre, tipo, parent_id?, subvencion_id?}` · Resp 201: `CentroCosteDTO` con `id` | 401 no autenticado; 403 sin permiso (SPEC-015); 409 `codigo` duplicado / `parent_id` de otra empresa / ciclo |
| `GET` | `/api/v1/centros` | Listado de centros de la empresa (árbol plano con `parent_id`) | Resp 200: `Pagina<CentroCosteDTO>` paginado, filtros `estado|tipo|padre` | 401; 403 |
| `GET` | `/api/v1/centros/{id}` | Detalle de un centro | Resp 200: `CentroCosteDTO` con `subvencion_id`, estado, hijos | 401; 403; 404 no existe o de otra empresa |
| `GET` | `/api/v1/centros/arbol` | Árbol jerárquico completo con cerradura (closure) resuelta | Resp 200: `CentroArbolDTO` con nodos y profundidad | 401; 403 |
| `PATCH` | `/api/v1/centros/{id}` | Edición de metadatos (nombre, tipo, padre, subvención) | Body parcial `CentroCostePatch` · Resp 200 | 401; 403; 404; 409 ciclo / subvención de otra empresa / `codigo` duplicado |
| `POST` | `/api/v1/centros/{id}/inactivar` | Inactivar (nunca borrar físico con historial) | Resp 200; importes no ya imputables | 401; 403; 404; 409 si ya inactivo |
| `POST` | `/api/v1/centros/{id}/reactivar` | Reactivar | Resp 200 | 401; 403; 404; 409 ya activo |
| `POST` | `/api/v1/asientos/{asiento_id}/lineas/{linea_id}/imputar` | Imputar una línea (borrador o pre-posteado en proceso de registro) a un centro | Body: `{centro_coste_id}` · Resp 200: `ImputacionDTO`; verifica centro de la empresa activa | 401; 403; 404 centro no existe / asiento o línea no existen / de otra empresa; 409 línea posteada (requiere rectificación); 422 centro inactivo |
| `DELETE` | `/api/v1/asientos/{asiento_id}/lineas/{linea_id}/imputar` | Quitar imputación (solo líneas de asiento borrador) | Resp 204 | 401; 403; 404; 409 línea posteada |
| `GET` | `/api/v1/informes/costes` | Informe de costes por centro y período | Query: `ejercicio>`, `fecha_desde?`, `fecha_hasta?`, `centro_id?`, `tipo (coste/ingreso/todos)` · Resp 200: `InformeCostesDTO` con filas `(centro_id, nombre, subtotal, hijos_subtotal)` | 401; 403; 404 centro inexistente; 422 período inválido |
| `GET` | `/api/v1/informes/costes/exportar` | Exportación CSV/JSON del informe (4 decimales) | Query igual que informe; `format=csv|json` · Resp 200 (attachment) | 401; 403; 422 |

### Notas de código

- **422**: cuerpo inválido (Pydantic v2) o estado inactivo del centro.
- **403 vs 404**: 403 para permisos; 404 para inexistencia real o cross-tenant (no revelar existencia).
- **Endpoints de informe**: agregan directamente líneas (SUM `NUMERIC(18,4)`), nunca campos calculados desde frontend.
- **Numero correlativo**: no aplica en esta feature (solo referencia a numeración del motor de asientos para rectificativos).

## Ficheros de formato externo

No aplica (SPEC-017 no intercambia ficheros normalizados con terceros). La exportación CSV/JSON del informe sigue el estándar del plan raíz (Decimal en 4 decimales, CSV delimiter `;`).