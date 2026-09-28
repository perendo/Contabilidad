import { ApiError } from "@/components/treasury/api";
import { cabecerasEmpresa } from "@/components/treasury/empresa";
import { get, getToken, requestBlob, request } from "@/services/client";

export { ApiError };

/** Lista cerrada de `documento_tipo` (research D17). El backend rechaza
 *  cualquier otro valor con 422 `tipo_documento_invalido`. */
export type TipoDocumento =
  | "factura"
  | "recibo"
  | "extracto"
  | "justificante"
  | "contrato"
  | "otro";

export const TIPOS_DOCUMENTO: { valor: TipoDocumento; etiqueta: string }[] = [
  { valor: "factura", etiqueta: "Factura" },
  { valor: "recibo", etiqueta: "Recibo o justificante de cobro" },
  { valor: "extracto", etiqueta: "Extracto bancario" },
  { valor: "justificante", etiqueta: "Justificante" },
  { valor: "contrato", etiqueta: "Contrato" },
  { valor: "otro", etiqueta: "Otro" },
];

export type EstadoDocumento = "activo" | "dado_de_baja";

export interface Documento {
  id: string;
  asiento_id: string;
  nombre_original: string;
  extension: string;
  content_type: string;
  size_bytes: number;
  num_paginas: number | null;
  sha256: string;
  tipo_documento: TipoDocumento;
  descripcion: string | null;
  importe_informativo: string | null;
  estado: EstadoDocumento;
  baja_motivo: string | null;
  baja_usuario: string | null;
  baja_at: string | null;
  created_by: string | null;
  created_at: string;
}

export interface EncabezadoAsiento {
  id: string;
  numero: number | null;
  fecha: string;
  ejercicio: number;
  concepto: string;
  estado: string;
}

export interface ListadoDocumentos {
  items: Documento[];
  total: number;
  documentos_obligatorios: false;
}

export type ItemGlobalDocumento = Documento & {
  journal_entry?: EncabezadoAsiento;
};

export interface ListadoGlobalDocumentos {
  items: ItemGlobalDocumento[];
  total: number;
  page: number;
  page_size: number;
}

export interface Rechazo {
  nombre: string;
  code: string;
  detail: string;
}

export interface ResultadoAdjunto {
  aceptados: Documento[];
  rechazados: Rechazo[];
}

export interface FiltrosDocumentos {
  asiento_id?: string;
  ejercicio?: number;
  tipo_documento?: TipoDocumento;
  estado?: EstadoDocumento;
  q?: string;
  incluir_bajas?: boolean;
  page?: number;
  page_size?: number;
}

/** Serializa filtros; los `undefined` se omiten para no viajar como `"undefined"`. */
function qs(params: Record<string, string | number | boolean | undefined>): string {
  const partes = Object.entries(params)
    .filter(([, valor]) => valor !== undefined && valor !== "")
    .map(
      ([clave, valor]) =>
        `${encodeURIComponent(clave)}=${encodeURIComponent(String(valor))}`
    );
  return partes.length ? `?${partes.join("&")}` : "";
}

const BASE = "/api/v1/documentos";

/** FR-018: una sola peticion con varios ficheros. Los validos se conservan y
 *  los rechazados vuelven con su `code`, que es lo que hace accionable el aviso
 *  (research D13). `FormData` no lleva `Content-Type`: lo pone el navegador con
 *  el `boundary`. */
export async function adjuntarDocumentos(
  asientoId: string,
  files: File[],
  tipoDocumento: TipoDocumento,
  descripcion?: string,
  importeInformativo?: string
): Promise<ResultadoAdjunto> {
  const form = new FormData();
  for (const fichero of files) {
    form.append("files", fichero, fichero.name);
  }
  form.append("tipo_documento", tipoDocumento);
  if (descripcion) form.append("descripcion", descripcion);
  if (importeInformativo) form.append("importe_informativo", importeInformativo);

  const cabeceras: Record<string, string> = { ...cabecerasEmpresa() };
  const token = getToken();
  if (token) cabeceras["Authorization"] = `Bearer ${token}`;

  const respuesta = await fetch(`${BASE}/asiento/${asientoId}`, {
    method: "POST",
    headers: cabeceras,
    body: form,
  });
  if (!respuesta.ok) {
    const cuerpo = (await respuesta.json().catch(() => ({}))) as {
      detail?: { detail?: string; code?: string };
    };
    throw new ApiError(
      respuesta.status,
      cuerpo.detail?.detail ?? `${respuesta.status} ${respuesta.statusText}`,
      cuerpo.detail?.code
    );
  }
  return (await respuesta.json()) as ResultadoAdjunto;
}

export function listarDocumentosAsiento(
  asientoId: string,
  incluirBajas = true
): Promise<ListadoDocumentos> {
  return get<ListadoDocumentos>(
    `${BASE}/asiento/${asientoId}${qs({ incluir_bajas: incluirBajas })}`
  );
}

export function listarDocumentos(
  filtros: FiltrosDocumentos = {}
): Promise<ListadoGlobalDocumentos> {
  return get<ListadoGlobalDocumentos>(
    `${BASE}${qs({
      asiento_id: filtros.asiento_id,
      ejercicio: filtros.ejercicio,
      tipo_documento: filtros.tipo_documento,
      estado: filtros.estado,
      q: filtros.q,
      incluir_bajas: filtros.incluir_bajas,
      page: filtros.page,
      page_size: filtros.page_size,
    })}`
  );
}

export function obtenerDocumento(id: string): Promise<Documento> {
  return get<Documento>(`${BASE}/${id}`);
}

/** Descarga autenticada. `requestBlob` (y no un `<a href>` plano) es lo que
 *  mantiene la sesion: una URL desnuda recibiria 401/403 (research D12). */
export function descargarDocumento(id: string, nombre: string): Promise<void> {
  return requestBlob(`${BASE}/${id}/descarga`).then((blob) => {
    const url = window.URL.createObjectURL(blob);
    const enlace = document.createElement("a");
    enlace.href = url;
    enlace.download = nombre;
    document.body.appendChild(enlace);
    enlace.click();
    document.body.removeChild(enlace);
    window.URL.revokeObjectURL(url);
  });
}

/** US3: baja logica. Solo admite el asiento en borrador; el backend responde
 *  409 `baja_no_permitida` sobre un asiento ya contabilizado. */
export function darDeBajaDocumento(id: string, motivo: string): Promise<unknown> {
  return request(`${BASE}/${id}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ motivo }),
  });
}

export function obtenerBlobDocumento(id: string): Promise<Blob> {
  return requestBlob(`${BASE}/${id}/descarga`);
}
