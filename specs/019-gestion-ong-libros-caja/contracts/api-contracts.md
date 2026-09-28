# API Contracts: Gestión ONG (Subvenciones, Libros Oficiales y Caja) (SPEC-019)

**Branch**: `019-gestion-ong-libros-caja` | **Date**: 2026-09-16 | **Spec**: [spec.md](spec.md)

**Convención empresa activa**: el `empresa_id` NUNCA viaja en la ruta ni en el body; se deriva exclusivamente de la cabecera/contexto de sesión autenticada (`X-Empresa-Activa`). Toda mutación/lectura filtra por ese `empresa_id`.

Prefix general: `/api/v1` (router `ngo`).

## REST

| Método | Ruta | Función | Body / Respuesta | Errores |
|---|---|---|---|---|
| `POST` | `/api/v1/subvenciones` | Registrar subvención | Body: `{entidad_concedente, programa, referencia?, importe_concedido, ejercicio, partidas?, observaciones?}` · Resp 201: `SubvencionDTO` estado `concedida` | 401 no autenticado; 403 sin permiso (SPEC-015); 409 referencia duplicada; 422 importe ≤ 0 / ejercicio inválido |
| `GET` | `/api/v1/subvenciones` | Listar (paginado, filtros estado/ejercicio) | Resp 200: `Pagina<SubvencionDTO>` (incluye pendiente y gastado) | 401; 403 |
| `GET` | `/api/v1/subvenciones/{id}` | Detalle con resumen (concedido/gastado/pendiente) | Resp 200: `SubvencionResumenDTO` | 401; 403; 404 |
| `PATCH` | `/api/v1/subvenciones/{id}` | Editar datos de control | Body parcial · Resp 200 | 401; 403; 404; 409 |
| `POST` | `/api/v1/subvenciones/{id}/estado` | Transición de estado (`en_curso`, `justificada`, `reintegrada`) | Body: `{estado}` · `reintegrada` exige `asiento_rectificativo_id` · Resp 200 | 401; 403; 404; 409 transición no permitida / falta rectificativo |
| `POST` | `/api/v1/subvenciones/{id}/gastos` | Imputar gasto (línea de asiento) | Body: `{asiento_id, linea_id, importe_asignado, partida?}` · Resp 201: `GastoImputadoDTO` | 401; 403; 404 línea/asiento de otra empresa o inexistente; 409 excede disponible / excede importe de la línea / doble imputación; 422 importe ≤ 0 |
| `DELETE` | `/api/v1/subvenciones/{id}/gastos/{gasto_id}` | Desimputar (rectificación solo administrativa previa a asentar) | Resp 204 | 401; 403; 404; 409 gasto ya usado en justificada/reintegrada |
| `GET` | `/api/v1/informes/subvenciones/{id}/justificacion` | Informe de justificación | Resp 200: `JustificacionDTO` (concedido, gastado, pendiente, detalle por línea, firmado por huella) | 401; 403; 404 |
| `GET` | `/api/v1/informes/subvenciones/{id}/justificacion/exportar` | Exportación CSV/JSON del informe | Query `format=csv|json` · Resp 200 (attachment) | 401; 403; 404; 422 |
| `POST` | `/api/v1/libros/{ejercicio}/generar` | Generar PDF de libros del ejercicio cerrado | Body: `{tipos: [diario, mayor, cuentas_anuales?]}` · Resp 201: `LibroGeneradoDTO[]` (tipo, sha256, url descarga) | 401; 403; 404 ejercicio inexistente; 409 ejercicio abierto |
| `GET` | `/api/v1/libros/{ejercicio}` | Listar libros generados del ejercicio | Resp 200: `Pagina<LibroDTO>` | 401; 403; 404 |
| `GET` | `/api/v1/libros/{id}/descarga` | Descargar PDF | Resp 200 `application/pdf` | 401; 403; 404 |
| `POST` | `/api/v1/legalizaciones` | Emitir fichero de legalización | Body: `{ejercicio, fecha_legalizacion?}` · Resp 201: `LegalizacionDTO` (empresa, ejercicio, rango, huella, descarga) | 401; 403; 404; 409 ejercicio abierto / re-emisión con huella distinta |
| `GET` | `/api/v1/legalizaciones` | Listar legalizaciones de la empresa | Resp 200: `Pagina<LegalizacionDTO>` | 401; 403 |
| `GET` | `/api/v1/legalizaciones/{id}/descarga` | Descargar fichero de legalización | Resp 200 según `legalizacion.md` | 401; 403; 404 |
| `POST` | `/api/v1/cajas` | Alta de caja/caja chica | Body: `{nombre, cuenta_570_id, tipo}` · Resp 201: `CajaDTO` | 401; 403; 404 cuenta 570 inexistente/inactiva; 409 570 ya asignada a otra caja / nombre duplicado |
| `GET` | `/api/v1/cajas` | Listar cajas | Resp 200: `Pagina<CajaDTO>` con saldo | 401; 403 |
| `GET` | `/api/v1/cajas/{id}` | Detalle con movimientos y saldo | Resp 200: `CajaDetalleDTO` | 401; 403; 404 |
| `GET` | `/api/v1/cajas/{id}/movimientos` | Listar movimientos (desde diario 570) | Query `fecha_desde|fecha_hasta` · Resp 200: `Pagina<MovimientoCajaDTO>` | 401; 403; 404 |
| `POST` | `/api/v1/cajas/{id}/movimientos` | Registrar movimiento (entrada/salida) | Body: `{tipo, importe, fecha, concepto, contrapartida_cuenta_id}` · Resp 201: `MovimientoCajaDTO` **con asiento_id del motor** | 401; 403; 404; 409 ejercicio cerrado; 422 importe ≤ 0 |
| `POST` | `/api/v1/cajas/{id}/arqueos` | Realizar arqueo | Body: `{fecha, efectivo_contado, detalle?}` · Resp 201: `ArqueoDTO` (saldo_libros, diferencia, estado) | 401; 403; 404; 422 |
| `POST` | `/api/v1/arqueos/{id}/aprobar` | Aprobar arqueo con diferencia | Body: `{asiento_ajuste_id}` (asiento balanceado que cuadra 570) · Resp 200: `ArqueoDTO` estado `aprobada` | 401; 403; 404; 409 ya aprobado/archivado / el ajuste no cuadra 570 con el efectivo / ajuste de otra empresa |
| `POST` | `/api/v1/arqueos/{id}/archivar` | Archivar arqueo con diferencia (queda pendiente visible) | Resp 200: `ArqueoDTO` estado `archivada` sin asiento | 401; 403; 404; 409 ya decidido |
| `GET` | `/api/v1/arqueos` | Listar arqueos de la empresa | Query `caja_id?|estado?` · Resp 200: `Pagina<ArqueoDTO>` | 401; 403 |

### Notas de código

- **422 vs 409**: 422 para datos inválidos; 409 para conflictos de estado/negocio (disponible, doble imputación, ejercicio abierto, huella distinta, 570 ya asignada, transición no permitida).
- **403 vs 404**: 403 permisos; 404 inexistencia real o cross-tenant.
- Los asientos de caja y de ajuste de arqueo los crea el motor (SPEC-002) con numeración correlativa y audit log; nunca se persisten fuera del motor.
- El `rango_asientos` de la legalización se lee del diario (inmutable), no se inventa.
- Documentos de formato externo: ver `contracts/libros-pdf.md` (PDF) y `contracts/legalizacion.md` (fichero de legalización).