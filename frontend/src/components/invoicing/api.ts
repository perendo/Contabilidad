import { ApiError } from "@/components/treasury/api";
import { cabecerasEmpresa } from "@/components/treasury/empresa";
import { getToken } from "@/services/client";

export type FacturaTipo = "VENTA" | "COMPRA" | "RECTIFICATIVA";
export type FacturaEstado = "borrador" | "emitida" | "anulada";

export interface SerieFactura {
  id: string;
  codigo: string;
  nombre: string;
  prefijo: string;
  sufijo: string;
  siguiente_numero: number;
  estado: "activa" | "inactiva";
  correlativo_ejemplo: string;
}

export interface FacturaLinea {
  id: string;
  line_no: number | null;
  descripcion: string;
  cantidad: string;
  precio_unitario: string;
  porcentaje_descuento: string;
  base: string;
  tipo_iva: string;
  cuota_iva: string;
  tipo_recargo: string;
  cuota_recargo: string;
  tipo_irpf: string;
  base_irpf: string;
  cuota_irpf: string;
}

export interface AsientoDetalle {
  id: string;
  numero_asiento: number | null;
  estado: string;
  tipo: string;
  asiento_original_id: string | null;
  total_debe: string;
  total_haber: string;
  lineas: { id: string; cuenta: string; debe: string; haber: string; detalle: string | null }[];
}

export interface Factura {
  id: string;
  empresa_id: number;
  serie_id: string;
  numero: string | null;
  numero_int: number | null;
  ejercicio: number;
  fecha: string;
  tipo: FacturaTipo;
  tercero_id: string;
  factura_original_id: string | null;
  concepto_global: string | null;
  importe_base: string;
  importe_iva: string;
  importe_recargo: string;
  importe_irpf: string;
  importe_total: string;
  regimen_caja: boolean;
  iva_devengado: boolean;
  estado: FacturaEstado;
  asiento_id: string | null;
  asiento: AsientoDetalle | null;
  lineas: FacturaLinea[];
}

export interface ListaFacturas {
  items: Factura[];
  total: number;
  page: number;
  page_size: number;
}

export interface LineaFacturaInput {
  descripcion?: string;
  cantidad?: string;
  precio_unitario: string;
  porcentaje_descuento?: string;
  tipo_iva?: string;
  tipo_recargo?: string;
  tipo_irpf?: string;
  base_irpf?: string;
}

export interface TerceroResumen {
  id: string;
  nombre: string;
  nif: string | null;
  es_cliente: boolean;
  es_proveedor: boolean;
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

export function listarSeries(): Promise<SerieFactura[]> {
  return llamar<SerieFactura[]>("/api/v1/facturacion/series");
}

export function crearSerie(body: {
  codigo: string;
  nombre?: string;
  prefijo?: string;
  sufijo?: string;
}): Promise<SerieFactura> {
  return llamar<SerieFactura>("/api/v1/facturacion/series", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function cambiarEstadoSerie(
  id: string,
  activa: boolean
): Promise<SerieFactura> {
  return llamar<SerieFactura>(`/api/v1/facturacion/series/${id}/estado`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ activa }),
  });
}

export function listarFacturas(
  filtros: {
    serie_id?: string;
    estado?: string;
    ejercicio?: number;
    fecha_desde?: string;
    fecha_hasta?: string;
    page?: number;
    page_size?: number;
  } = {}
): Promise<ListaFacturas> {
  const params = new URLSearchParams();
  if (filtros.serie_id) params.set("serie_id", filtros.serie_id);
  if (filtros.estado) params.set("estado", filtros.estado);
  if (filtros.ejercicio) params.set("ejercicio", String(filtros.ejercicio));
  if (filtros.fecha_desde) params.set("fecha_desde", filtros.fecha_desde);
  if (filtros.fecha_hasta) params.set("fecha_hasta", filtros.fecha_hasta);
  if (filtros.page) params.set("page", String(filtros.page));
  if (filtros.page_size) params.set("page_size", String(filtros.page_size));
  const qs = params.toString();
  return llamar<ListaFacturas>(`/api/v1/facturacion/facturas${qs ? `?${qs}` : ""}`);
}

export function obtenerFactura(id: string): Promise<Factura> {
  return llamar<Factura>(`/api/v1/facturacion/facturas/${id}`);
}

export function crearFactura(body: {
  serie_id: string;
  ejercicio: number;
  fecha: string;
  tipo: string;
  tercero_id: string;
  concepto_global?: string;
  regimen_caja?: boolean;
  lineas: LineaFacturaInput[];
}): Promise<Factura> {
  return llamar<Factura>("/api/v1/facturacion/facturas", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function emitirFactura(id: string): Promise<{
  id: string;
  numero: string;
  estado: string;
  asiento_id: string;
  numero_asiento: number | null;
}> {
  return llamar<{
    id: string;
    numero: string;
    estado: string;
    asiento_id: string;
    numero_asiento: number | null;
  }>(`/api/v1/facturacion/facturas/${id}/emitir`, { method: "POST" });
}

export function anularFactura(id: string): Promise<{ id: string; estado: string }> {
  return llamar<{ id: string; estado: string }>(
    `/api/v1/facturacion/facturas/${id}/anular`,
    { method: "POST" }
  );
}

export function rectificarFactura(
  id: string,
  body: { serie_id: string; motivo: string; lineas?: LineaFacturaInput[] }
): Promise<Factura> {
  return llamar<Factura>(`/api/v1/facturacion/facturas/${id}/rectificar`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function eliminarFactura(id: string): Promise<void> {
  return llamar<void>(`/api/v1/facturacion/facturas/${id}`, { method: "DELETE" });
}

export function listarTerceros(rol: "cliente" | "proveedor"): Promise<{
  total: number;
  items: TerceroResumen[];
}> {
  return llamar<{ total: number; items: TerceroResumen[] }>(
    `/api/v1/terceros?rol=${rol}&limit=100`
  );
}

export function formatearImporte(importe: string): string {
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "EUR",
  }).format(Number(importe));
}
