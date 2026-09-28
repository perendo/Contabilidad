import { ApiError } from "@/components/treasury/api";
import { cabecerasEmpresa } from "@/components/treasury/empresa";
import { getToken } from "@/services/client";

export interface OperacionLibro {
  factura_id: string;
  nif_tercero: string | null;
  nombre_tercero: string;
  fecha_expedicion: string;
  num_factura: string | null;
  base: string;
  cuota: string;
  tipo_iva: string;
  recargo_cuota: string;
  incluir_303: boolean;
  es_intracomunitaria: boolean;
}

export interface LibroIva {
  ejercicio: number;
  periodo: number | null;
  tipo_libro: string;
  operaciones: OperacionLibro[];
  total_base: string;
  total_cuota: string;
  total_recargo: string;
  n_operaciones: number;
}

export interface Modelo303 {
  ejercicio: number;
  periodo: number;
  devengado: Record<string, { base: string; cuota: string }>;
  deducible: Record<string, { base: string; cuota: string }>;
  recargo_equivalencia: { cuota: string };
  resultado: { a_ingresar: string; a_compensar: string };
  iva_diferido: { pendiente: string };
  cuadre_libros: boolean;
}

export interface Modelo347 {
  ejercicio: number;
  operaciones: {
    nif_tercero: string;
    nombre: string;
    clave_operacion: string;
    importe_acumulado: string;
    n_operaciones: number;
  }[];
  total_general: string;
}

export interface Modelo349 {
  ejercicio: number;
  periodo: number;
  operaciones: {
    nif_tercero: string;
    clave_operacion: string;
    tipo_operacion: string;
    importe: string;
  }[];
  total_general: string;
}

export interface Exportacion {
  exportacion_id: string;
  numero_exportacion: number;
  modelo: string;
  ejercicio: number;
  periodo: string | null;
  fecha: string;
  usuario: string | null;
  sha256: string;
  estado: string;
  advertencia: string | null;
}

type DetalleError = { code?: string; detail?: string };

async function llamar<T>(ruta: string, opciones: RequestInit = {}): Promise<T> {
  const cabeceras: Record<string, string> = {
    ...((opciones.headers as Record<string, string> | undefined) ?? {}),
  };
  const token = getToken();
  if (token) cabeceras["Authorization"] = `Bearer ${token}`;
  Object.assign(cabeceras, cabecerasEmpresa());
  const respuesta = await fetch(ruta, { ...opciones, headers: cabeceras });
  const cuerpo = (await respuesta.json().catch(() => ({}))) as {
    detail?: string | DetalleError;
  };
  if (!respuesta.ok) {
    const detalle = cuerpo.detail;
    const mensaje =
      typeof detalle === "string"
        ? detalle
        : detalle?.detail ?? `${respuesta.status} ${respuesta.statusText}`;
    const code = typeof detalle === "object" ? detalle?.code : undefined;
    throw new ApiError(respuesta.status, mensaje, code);
  }
  return cuerpo as T;
}

function qs(params: Record<string, string | number | undefined>): string {
  const buscador = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== "") buscador.set(k, String(v));
  });
  return buscador.toString();
}

export function obtenerLibro(
  tipo: string,
  ejercicio: number,
  periodo: number,
  tipoPeriodo: string
): Promise<LibroIva> {
  return llamar<LibroIva>(
    `/api/v1/libros-iva/${tipo}?${qs({ ejercicio, periodo, tipo_periodo: tipoPeriodo })}`
  );
}

export function obtener303(
  ejercicio: number,
  periodo: number,
  tipoPeriodo: string
): Promise<Modelo303> {
  return llamar<Modelo303>(
    `/api/v1/modelos/303?${qs({ ejercicio, periodo, tipo_periodo: tipoPeriodo })}`
  );
}

export function obtener347(ejercicio: number): Promise<Modelo347> {
  return llamar<Modelo347>(`/api/v1/modelos/347?${qs({ ejercicio })}`);
}

export function obtener349(
  ejercicio: number,
  periodo: number,
  tipoPeriodo: string
): Promise<Modelo349> {
  return llamar<Modelo349>(
    `/api/v1/modelos/349?${qs({ ejercicio, periodo, tipo_periodo: tipoPeriodo })}`
  );
}

export function listarExportaciones(ejercicio?: number): Promise<{ items: Exportacion[] }> {
  return llamar(`/api/v1/exportaciones?${qs({ ejercicio })}`);
}

export function crearExportacion(body: {
  modelo: string;
  ejercicio: number;
  periodo?: number;
  tipo_periodo?: string;
  formato?: string;
}): Promise<Exportacion> {
  return llamar<Exportacion>("/api/v1/exportaciones", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function descargarExportacion(id: string, nombre: string): Promise<void> {
  const cabeceras: Record<string, string> = {};
  const token = getToken();
  if (token) cabeceras["Authorization"] = `Bearer ${token}`;
  Object.assign(cabeceras, cabecerasEmpresa());
  const respuesta = await fetch(`/api/v1/exportaciones/${id}/descargar`, {
    headers: cabeceras,
  });
  if (!respuesta.ok) throw new ApiError(respuesta.status, "No se pudo descargar");
  const blob = await respuesta.blob();
  const url = URL.createObjectURL(blob);
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombre;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  URL.revokeObjectURL(url);
}

export function formatearImporte(importe: string): string {
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "EUR",
  }).format(Number(importe));
}