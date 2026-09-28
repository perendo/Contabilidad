import { ApiError } from "@/components/treasury/api";
import { get, post, put, requestBlob } from "@/services/client";

export { ApiError };

export type TipoExportacion = "INTEGRAL" | "SII";
export type EstadoExportacion = "en_proceso" | "lista" | "fallida";

export interface LineaManifiesto {
  bloque: string;
  fichero: string | null;
  ruta: string | null;
  descripcion: string | null;
  entidades_exportadas: string[];
  conteo_registros: number;
  sha256: string | null;
  fecha_min: string | null;
  fecha_max: string | null;
  ejercicio_min: number | null;
  ejercicio_max: number | null;
}

export interface ResumenManifiesto {
  id: string | null;
  formato_version: string | null;
  fecha_generacion: string | null;
  tenant_id: number;
  ejercicio_desde: number | null;
  ejercicio_hasta: number | null;
  n_bloques: number;
  sha256_fichero: string | null;
  bloques: LineaManifiesto[];
}

export interface Exportacion {
  exportacion_id: string;
  numero_exportacion: number;
  anio_creacion: number;
  tipo: TipoExportacion;
  estado: EstadoExportacion;
  ejercicio_desde: number | null;
  ejercicio_hasta: number | null;
  creado_por: string | null;
  created_at: string | null;
  completado_at: string | null;
  sha256: string | null;
  tamano_bytes: number | null;
  tamano_mb: string;
  n_bloques: number;
  mensaje_error: string | null;
  descargable?: boolean;
  sha256_contenido?: string;
  nombre_fichero?: string;
}

export interface ListadoExportaciones {
  items: Exportacion[];
  total: number;
  page: number;
}

export interface DetalleExportacion extends Exportacion {
  manifiesto: ResumenManifiesto;
}

export interface Verificacion {
  integro: boolean;
  sha256_calculado: string;
  sha256_manifiesto: string | null;
  sha256_contenido: string;
  sha256_contenido_manifiesto: string | null;
  exportacion_id: string;
  numero_exportacion: number;
  verificada_at: string | null;
  bloques: { bloque: string; esperados: number; encontrados: number; coincide: boolean }[];
  diferencias: {
    tipo: string;
    esperado: unknown;
    encontrado: unknown;
    detalle: string;
    bloque?: string;
  }[];
}

export interface ConfigSii {
  obligado_sii: boolean;
  sin_anexo: boolean;
  clave_regimen: string;
  entidad_representante_id: string | null;
  fecha_alta: string | null;
}

export interface BloqueSii {
  nombre: string;
  conteo: number;
  registros: Record<string, string>[];
}

const BASE = "/api/v1/exportaciones";

function qs(params: Record<string, string | number | undefined>): string {
  const entrada = new URLSearchParams();
  for (const [clave, valor] of Object.entries(params)) {
    if (valor !== undefined && valor !== "") entrada.append(clave, String(valor));
  }
  const texto = entrada.toString();
  return texto ? `?${texto}` : "";
}

export function listarExportaciones(
  params: { tipo?: TipoExportacion; estado?: EstadoExportacion; page?: number; page_size?: number } = {}
): Promise<ListadoExportaciones> {
  return get<ListadoExportaciones>(`${BASE}${qs(params)}`);
}

/** El `empresa_id` nunca viaja: lo resuelve el backend desde la sesion. */
export function crearExportacion(body: {
  tipo?: TipoExportacion;
  ejercicio_desde?: number;
  ejercicio_hasta?: number;
}): Promise<Exportacion> {
  return post<Exportacion>(BASE, body);
}

export function obtenerExportacion(exportacionId: string): Promise<DetalleExportacion> {
  return get<DetalleExportacion>(`${BASE}/${exportacionId}`);
}

export function verificarExportacion(exportacionId: string): Promise<Verificacion> {
  return post<Verificacion>(`${BASE}/${exportacionId}/verificar`);
}

export function obtenerConfigSii(): Promise<ConfigSii> {
  return get<ConfigSii>(`${BASE}/sii/config`);
}

export function guardarConfigSii(body: {
  obligado_sii?: boolean;
  sin_anexo?: boolean;
  clave_regimen?: string | null;
}): Promise<ConfigSii> {
  return put<ConfigSii>(`${BASE}/sii/config`, body);
}

export async function obtenerBloqueSii(exportacionId: string): Promise<{
  config: ConfigSii;
  bloques_sii: BloqueSii[];
}> {
  return get(`${BASE}/${exportacionId}/sii`);
}

/**
 * Descarga el ZIP con la sesion y la empresa activa (`requestBlob` anade el JWT
 * y la cabecera `X-Empresa-Activa`); una `<a href>` plana daria 401/403.
 */
export async function descargarExportacion(exportacionId: string): Promise<void> {
  const blob = await requestBlob(`${BASE}/${exportacionId}/descarga`);
  const url = URL.createObjectURL(blob);
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = `exportacion-${exportacionId}.zip`;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  URL.revokeObjectURL(url);
}

/** Importes viajan como cadenas de 4 decimales; solo se formatean al pintar. */
export function formatearBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MiB`;
}

export const ETIQUETA_ESTADO: Record<EstadoExportacion, string> = {
  en_proceso: "En proceso",
  lista: "Lista",
  fallida: "Fallida",
};

export const EJERCICIO_POR_DEFECTO = new Date().getFullYear();
