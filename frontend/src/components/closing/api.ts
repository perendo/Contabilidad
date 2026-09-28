import { ApiError } from "@/components/treasury/api";
import { get, post } from "@/services/client";

export { ApiError };

export type TipoPeriodo = "MES" | "TRIMESTRE";
export type EstadoPeriodo =
  | "abierto"
  | "cerrado"
  | "reabierto_ajuste"
  | "cerrado_ajustado";
export type TipoPeriodoReapertura = "MES" | "TRIMESTRE" | "ANUAL";
export type EstadoSolicitud =
  | "pendiente"
  | "aprobada"
  | "reabierta"
  | "cerrada"
  | "rechazada";
export type EstadoCierreEjercicio = "completado" | "reapertura_pendiente";

export interface LineaBalanza {
  cuenta_id: number;
  codigo: string;
  nombre: string;
  nivel: number;
  debe: string;
  haber: string;
  saldo: string;
}

export interface ResumenBalanza {
  id: string;
  total_debe: string;
  total_haber: string;
  cuadra: boolean;
  n_lineas: number;
  sha256: string;
}

export interface Balanza extends ResumenBalanza {
  periodo_id: string;
  ejercicio: number;
  fecha_ini: string;
  fecha_fin: string;
  fecha_generacion: string;
  resultado_provisional: string;
  lineas: LineaBalanza[];
}

export interface PeriodoCerrado {
  periodo_id: string;
  ejercicio: number;
  tipo: TipoPeriodo;
  periodo: number;
  fecha_ini: string;
  fecha_fin: string;
  estado: EstadoPeriodo;
  n_reaperturas: number;
  balanza_id: string | null;
  cerrado_at: string | null;
  cerrado_por: string | null;
}

export interface ResultadoCierre extends PeriodoCerrado {
  balanza: ResumenBalanza;
  resultado_provisional: string;
}

export interface ListadoPeriodos {
  items: PeriodoCerrado[];
  total: number;
  page: number;
}

export interface CierreEjercicio {
  cierre_id: string;
  ejercicio: number;
  estado: EstadoCierreEjercicio;
  fecha_cierre: string;
  resultado_ejercicio: string;
  asiento_regularizacion_id: string | null;
  asiento_cierre_id: string | null;
  asiento_apertura_id: string | null;
  cerrado_por: string | null;
  cerrado_at: string;
}

export interface SolicitudReapertura {
  solicitud_id: string;
  numero_solicitud: number;
  ejercicio: number;
  periodo_id: string | null;
  tipo_periodo: TipoPeriodoReapertura;
  periodo: number | null;
  motivo: string;
  estado: EstadoSolicitud;
  usuario_solicitante: string | null;
  fecha_solicitud: string;
  aprobada_por: string | null;
  fecha_aprobacion: string | null;
  asiento_rectificacion_id: string | null;
  fecha_cierre_efectivo: string | null;
  nota_impacto: string | null;
}

export interface DetalleSolicitud extends SolicitudReapertura {
  /** Periodo asociado a la solicitud; `null` en la reapertura del ejercicio. */
  periodo_cerrado: PeriodoCerrado | null;
}

export interface ListadoSolicitudes {
  items: SolicitudReapertura[];
  total: number;
  page: number;
}

const BASE = "/api/v1/cierres";

function qs(params: Record<string, string | number | undefined>): string {
  const entrada = new URLSearchParams();
  for (const [clave, valor] of Object.entries(params)) {
    if (valor !== undefined && valor !== "") entrada.append(clave, String(valor));
  }
  const texto = entrada.toString();
  return texto ? `?${texto}` : "";
}

export function listarPeriodos(
  params: {
    ejercicio?: number;
    tipo?: TipoPeriodo;
    estado?: EstadoPeriodo;
    page?: number;
    page_size?: number;
  } = {}
): Promise<ListadoPeriodos> {
  return get<ListadoPeriodos>(`${BASE}/intermedios${qs(params)}`);
}

export function cerrarPeriodo(body: {
  ejercicio: number;
  tipo: TipoPeriodo;
  periodo: number;
}): Promise<ResultadoCierre> {
  return post<ResultadoCierre>(`${BASE}/intermedios`, body);
}

export function obtenerBalanza(periodoId: string): Promise<Balanza> {
  return get<Balanza>(`${BASE}/intermedios/${periodoId}/balanza`);
}

export function cerrarEjercicioAnual(body: { ejercicio: number }): Promise<CierreEjercicio> {
  return post<CierreEjercicio>(`${BASE}/anual`, body);
}

export function obtenerCierreAnual(ejercicio: number): Promise<CierreEjercicio> {
  return get<CierreEjercicio>(`${BASE}/anual/${ejercicio}`);
}

export function solicitarReapertura(body: {
  ejercicio: number;
  tipo_periodo: TipoPeriodoReapertura;
  periodo?: number | null;
  motivo: string;
  nota_impacto?: string | null;
}): Promise<SolicitudReapertura> {
  return post<SolicitudReapertura>(`${BASE}/reaperturas`, body);
}

export function aprobarReapertura(solicitudId: string): Promise<SolicitudReapertura> {
  return post<SolicitudReapertura>(`${BASE}/reaperturas/${solicitudId}/aprobar`);
}

export function rechazarReapertura(solicitudId: string): Promise<SolicitudReapertura> {
  return post<SolicitudReapertura>(`${BASE}/reaperturas/${solicitudId}/rechazar`);
}

export function rectificarReapertura(
  solicitudId: string,
  asientoId: string
): Promise<SolicitudReapertura> {
  return post<SolicitudReapertura>(`${BASE}/reaperturas/${solicitudId}/rectificar`, {
    asiento_id: asientoId,
  });
}

export function listarReaperturas(
  params: {
    ejercicio?: number;
    estado?: EstadoSolicitud;
    tipo_periodo?: TipoPeriodoReapertura;
    page?: number;
    page_size?: number;
  } = {}
): Promise<ListadoSolicitudes> {
  return get<ListadoSolicitudes>(`${BASE}/reaperturas${qs(params)}`);
}

export function obtenerReapertura(solicitudId: string): Promise<DetalleSolicitud> {
  return get<DetalleSolicitud>(`${BASE}/reaperturas/${solicitudId}`);
}

/** Importes viajan como cadenas de 4 decimales; solo se formatean al pintar. */
export function formatearImporte(importe: string | null | undefined): string {
  if (importe === null || importe === undefined) return "—";
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 4,
    maximumFractionDigits: 4,
  }).format(Number(importe));
}

export const MESES = [
  "Enero",
  "Febrero",
  "Marzo",
  "Abril",
  "Mayo",
  "Junio",
  "Julio",
  "Agosto",
  "Septiembre",
  "Octubre",
  "Noviembre",
  "Diciembre",
];

export const ETIQUETA_ESTADO: Record<EstadoPeriodo, string> = {
  abierto: "Abierto",
  cerrado: "Cerrado",
  reabierto_ajuste: "Reabierto (ajuste)",
  cerrado_ajustado: "Cerrado (ajustado)",
};

export const ETIQUETA_SOLICITUD: Record<EstadoSolicitud, string> = {
  pendiente: "Pendiente",
  aprobada: "Aprobada",
  reabierta: "Reabierta",
  cerrada: "Cerrada",
  rechazada: "Rechazada",
};
