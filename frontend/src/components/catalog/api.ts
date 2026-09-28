import { get, getToken, post } from "@/services/client";
import { cabecerasEmpresa } from "@/components/treasury/empresa";

import { ApiError } from "@/components/treasury/api";

export { ApiError };

export type EstadoVersion = "borrador" | "vigente" | "anulada";
export type EstadoCuenta = "igual" | "nueva" | "renombrada" | "suprimida";
export type TipoMovimiento = "igual" | "renombrada" | "suprimida" | "nueva";
export type TipoOperacion = "alta" | "renombrado" | "baja";

export interface VersionResumen {
  id: string;
  numero_version: number;
  codigo: string;
  fecha_inicio: string;
  fecha_fin: string | null;
  estado: EstadoVersion;
  es_migracion: boolean;
  resolucion?: string;
}

export interface CuentaVersion {
  id: string;
  account_id: number;
  codigo_version: string;
  nombre_version: string;
  estado: EstadoCuenta;
  parent_version_id: string | null;
}

export interface MapeoVersion {
  id: string;
  version_origen_id: string;
  cuenta_origen_id: string | null;
  cuenta_destino_id: string | null;
  tipo_movimiento: TipoMovimiento;
  requiere_reclasificacion: boolean;
  origen: "manifiesto" | "autogenerado";
}

export interface VersionDetalle extends VersionResumen {
  creado_por?: string | null;
  cuentas: CuentaVersion[];
  mapeos: MapeoVersion[];
}

export interface ListadoVersiones {
  items: VersionResumen[];
  total: number;
}

export interface OperacionImport {
  operacion: TipoOperacion;
  codigo: string;
  nombre?: string | null;
  padre_codigo?: string | null;
  destino_codigo?: string | null;
}

export interface VersionNueva {
  codigo: string;
  fecha_inicio: string;
  fecha_fin?: string | null;
  cuentas: OperacionImport[];
}

export interface PendienteMapeo {
  codigo: string;
  motivo: string;
}

export interface ResultadoImport {
  version_id: string;
  nuevas: number;
  renombradas: number;
  suprimidas: number;
  mapeos: number;
  pendientes_mapeo: PendienteMapeo[];
}

export interface ItemReclasif {
  cuenta_origen_id: number;
  codigo_origen: string;
  importe: string;
  cuenta_destino_id: string;
  codigo_destino: string;
  mapeo_id: string;
}

export interface PreviewReclasif {
  version_id: string;
  origen_version_id: string;
  items: ItemReclasif[];
  total_importe: string;
}

export interface AsientoReclasif {
  asiento_id: string;
  numero_asiento: number;
  cuadre: boolean;
}

export interface ResultadoConfirm {
  reclasificaciones: number;
  asientos: AsientoReclasif[];
  total_importe: string;
}

function qs(params: Record<string, string | number | undefined>): string {
  const entrada = new URLSearchParams();
  for (const [clave, valor] of Object.entries(params)) {
    if (valor !== undefined && valor !== "") entrada.append(clave, String(valor));
  }
  const texto = entrada.toString();
  return texto ? `?${texto}` : "";
}

export function listarVersiones(
  params: Record<string, string | number | undefined> = {}
): Promise<ListadoVersiones> {
  return get<ListadoVersiones>(`/api/v1/catalogo/versiones${qs(params)}`);
}

export function crearVersion(body: VersionNueva): Promise<VersionResumen> {
  return post<VersionResumen>("/api/v1/catalogo/versiones", body);
}

export function obtenerVersion(id: string): Promise<VersionDetalle> {
  return get<VersionDetalle>(`/api/v1/catalogo/versiones/${id}`);
}

export function activarVersion(id: string): Promise<VersionResumen> {
  return post<VersionResumen>(`/api/v1/catalogo/versiones/${id}/activar`);
}

export function versionVigente(fecha: string): Promise<VersionResumen> {
  return get<VersionResumen>(`/api/v1/catalogo/vigente${qs({ fecha })}`);
}

export function cuentasVersion(
  versionId: string,
  q = ""
): Promise<{ items: Omit<CuentaVersion, "id" | "parent_version_id">[] }> {
  return get(`/api/v1/catalogo/cuentas${qs({ version_id: versionId, q })}`);
}

export async function importarCatalogo(
  file: File,
  codigoVersion: string,
  fechaInicio: string,
  fechaFin?: string
): Promise<ResultadoImport> {
  const datos = new FormData();
  datos.append("file", file);
  datos.append("codigo_version", codigoVersion);
  datos.append("fecha_inicio", fechaInicio);
  if (fechaFin) datos.append("fecha_fin", fechaFin);
  const cabeceras: Record<string, string> = {};
  const token = getToken();
  if (token) cabeceras["Authorization"] = `Bearer ${token}`;
  Object.assign(cabeceras, cabecerasEmpresa());
  const respuesta = await fetch("/api/v1/catalogo/importar", {
    method: "POST",
    headers: cabeceras,
    body: datos,
  });
  const cuerpo = (await respuesta.json().catch(() => ({}))) as {
    detail?: string | { detail?: string; code?: string };
  };
  if (!respuesta.ok) {
    const detalle = cuerpo.detail;
    const mensaje =
      typeof detalle === "string"
        ? detalle
        : detalle?.detail ?? `${respuesta.status} ${respuesta.statusText}`;
    const code = typeof detalle === "object" ? detalle.code : undefined;
    throw new ApiError(respuesta.status, mensaje, code);
  }
  return cuerpo as unknown as ResultadoImport;
}

export function previewReclasificacion(
  versionId: string,
  ejercicio: number
): Promise<PreviewReclasif> {
  return get(
    `/api/v1/catalogo/reclasificar/preview${qs({ version_id: versionId, ejercicio })}`
  );
}

export function confirmarReclasificacion(
  versionId: string,
  ejercicio: number,
  items: ItemReclasif[] | null
): Promise<ResultadoConfirm> {
  return post("/api/v1/catalogo/reclasificar/confirmar", {
    version_id: versionId,
    ejercicio,
    items,
  });
}
