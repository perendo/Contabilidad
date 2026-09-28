import { getToken } from "@/services/client";
import { cabecerasEmpresa } from "../treasury/empresa";

export type SubvencionEstado = "concedida" | "en_curso" | "justificada" | "reintegrada";
export type TipoLibro = "diario" | "mayor" | "balance" | "pyg";

export interface Subvencion {
  id: string;
  entidad_concedente: string;
  programa: string;
  referencia: string | null;
  importe_concedido: string;
  ejercicio: number;
  estado: SubvencionEstado;
  partidas: string[] | null;
  observaciones: string | null;
  gastado: string;
  pendiente: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface GastoInforme {
  id: string;
  asiento_id: string;
  numero_asiento: number | null;
  fecha: string | null;
  cuenta: string | null;
  importe: string;
  partida: string | null;
}

export interface InformeJustificacion {
  id: string;
  entidad_concedente: string;
  programa: string;
  referencia: string | null;
  importe_concedido: string;
  gastado: string;
  pendiente: string;
  estado: SubvencionEstado;
  partidas: string[] | null;
  detalle: GastoInforme[];
  huella: string;
}

export interface ListaPaginada<T> {
  items: T[];
  total: number;
  page?: number;
  page_size?: number;
}

export interface Libro {
  id: string;
  ejercicio: number;
  tipo: TipoLibro;
  sha256: string;
  size_bytes: number;
  url: string;
}

export interface LibroGenerado {
  tipo: TipoLibro;
  sha256: string;
  url: string;
  size_bytes: number;
  reusado: boolean;
}

export interface Legalizacion {
  id: string;
  ejercicio: number;
  rango_asientos_desde: number;
  rango_asientos_hasta: number;
  total_asientos: number;
  huella: string;
  fecha_emision: string | null;
  fecha_legalizacion: string | null;
  valido: boolean;
  motivo_reemision: string | null;
  url: string;
}

export interface Caja {
  id: string;
  nombre: string;
  cuenta_570_id: number;
  tipo: string;
  estado: "activa" | "inactiva";
  saldo: string;
}

export interface Movimiento {
  id: string;
  caja_id: string;
  asiento_id: string;
  linea_id: string;
  tipo: "entrada" | "salida";
  importe: string;
  fecha: string;
  created_at: string | null;
}

export interface DetalleCaja extends Caja {
  movimientos: ListaPaginada<Movimiento>;
}

export interface Arqueo {
  id: string;
  caja_id: string;
  fecha: string;
  saldo_libros: string;
  efectivo_contado: string;
  diferencia: string;
  estado: "cuadra" | "con_diferencia";
  decision: "pendiente" | "aprobada" | "rechazada" | null;
  asiento_ajuste_id: string | null;
  archivado: boolean;
  detalle_diferencia: string | null;
  created_at: string | null;
}

export interface LineaAsiento {
  id: string;
  cuenta: string;
  debe: string;
  haber: string;
  detalle: string | null;
  centro_coste_id: string | null;
}

export interface Asiento {
  id: string;
  numero_asiento: number;
  fecha: string;
  concepto: string;
  estado: string;
  total_debe: string;
  total_haber: string;
  n_lineas: number;
  lineas?: LineaAsiento[];
}

export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(status: number, message: string, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function manejar(respuesta: Response): Promise<unknown> {
  const cuerpo = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    const detalle = cuerpo?.detail;
    const mensaje =
      typeof detalle === "string"
        ? detalle
        : detalle?.detail ?? `${respuesta.status} ${respuesta.statusText}`;
    throw new ApiError(respuesta.status, mensaje, detalle?.code);
  }
  return cuerpo;
}

async function descargar(ruta: string, nombre: string): Promise<void> {
  const respuesta = await fetch(ruta, { headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() } });
  if (!respuesta.ok) {
    throw new ApiError(respuesta.status, "No se pudo descargar el fichero");
  }
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
  const numero = Number(importe);
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "EUR",
  }).format(numero);
}

export function paginar(filtros: { page?: number; page_size?: number } = {}): string {
  const params = new URLSearchParams();
  if (filtros.page) params.set("page", String(filtros.page));
  if (filtros.page_size) params.set("page_size", String(filtros.page_size));
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export async function listarSubvenciones(
  filtros: { estado?: SubvencionEstado; ejercicio?: number; page?: number; page_size?: number } = {}
): Promise<ListaPaginada<Subvencion>> {
  const params = new URLSearchParams();
  if (filtros.estado) params.set("estado", filtros.estado);
  if (filtros.ejercicio) params.set("ejercicio", String(filtros.ejercicio));
  if (filtros.page) params.set("page", String(filtros.page));
  if (filtros.page_size) params.set("page_size", String(filtros.page_size));
  const respuesta = await fetch(`/api/v1/subvenciones?${params.toString()}`, {
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as ListaPaginada<Subvencion>;
}

export async function obtenerSubvencion(id: string): Promise<Subvencion> {
  const respuesta = await fetch(`/api/v1/subvenciones/${id}`, {
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as Subvencion;
}

export async function crearSubvencion(body: {
  entidad_concedente: string;
  programa: string;
  referencia?: string | null;
  importe_concedido: string;
  ejercicio: number;
  partidas?: string[] | null;
  observaciones?: string | null;
}): Promise<Subvencion> {
  const respuesta = await fetch("/api/v1/subvenciones", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
    body: JSON.stringify(body),
  });
  return (await manejar(respuesta)) as Subvencion;
}

export async function editarSubvencion(
  id: string,
  body: {
    entidad_concedente?: string;
    programa?: string;
    referencia?: string | null;
    observaciones?: string | null;
    partidas?: string[] | null;
  }
): Promise<Subvencion> {
  const respuesta = await fetch(`/api/v1/subvenciones/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
    body: JSON.stringify(body),
  });
  return (await manejar(respuesta)) as Subvencion;
}

export async function cambiarEstadoSubvencion(
  id: string,
  estado: SubvencionEstado,
  asiento_rectificativo_id?: string | null
): Promise<Subvencion> {
  const respuesta = await fetch(`/api/v1/subvenciones/${id}/estado`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
    body: JSON.stringify({ estado, asiento_rectificativo_id }),
  });
  return (await manejar(respuesta)) as Subvencion;
}

export async function imputarGasto(
  subvencionId: string,
  body: { asiento_id: string; linea_id: string; importe_asignado: string; partida?: string | null }
): Promise<Record<string, unknown>> {
  const respuesta = await fetch(`/api/v1/subvenciones/${subvencionId}/gastos`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
    body: JSON.stringify(body),
  });
  return (await manejar(respuesta)) as Record<string, unknown>;
}

export async function desimputarGasto(subvencionId: string, gastoId: string): Promise<void> {
  const respuesta = await fetch(`/api/v1/subvenciones/${subvencionId}/gastos/${gastoId}`, {
    method: "DELETE",
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
  });
  await manejar(respuesta);
}

export async function listarAsientos(
  filtros: { page?: number; page_size?: number } = {}
): Promise<ListaPaginada<Asiento>> {
  const params = new URLSearchParams();
  if (filtros.page) params.set("page", String(filtros.page));
  if (filtros.page_size) params.set("page_size", String(filtros.page_size));
  const respuesta = await fetch(`/api/v1/asientos?${params.toString()}`, {
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as ListaPaginada<Asiento>;
}

export async function obtenerAsiento(id: string): Promise<Asiento> {
  const respuesta = await fetch(`/api/v1/asientos/${id}`, {
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as Asiento;
}

export async function obtenerInforme(subvencionId: string): Promise<InformeJustificacion> {
  const respuesta = await fetch(`/api/v1/informes/subvenciones/${subvencionId}/justificacion`, {
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as InformeJustificacion;
}

export async function exportarInforme(subvencionId: string, formato: "csv" | "json"): Promise<void> {
  await descargar(
    `/api/v1/informes/subvenciones/${subvencionId}/justificacion/exportar?formato=${formato}`,
    `justificacion-${subvencionId}.${formato}`
  );
}

export async function generarLibros(ejercicio: number, tipos: TipoLibro[]): Promise<LibroGenerado[]> {
  const respuesta = await fetch(`/api/v1/libros/${ejercicio}/generar`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
    body: JSON.stringify({ tipos }),
  });
  return (await manejar(respuesta)) as LibroGenerado[];
}

export async function listarLibros(ejercicio: number): Promise<ListaPaginada<Libro>> {
  const respuesta = await fetch(`/api/v1/libros/${ejercicio}`, {
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as ListaPaginada<Libro>;
}

export async function descargarLibro(id: string): Promise<void> {
  await descargar(`/api/v1/libros/${id}/descarga`, `libro-${id}.pdf`);
}

export async function emitirLegalizacion(
  ejercicio: number,
  fecha_legalizacion?: string | null
): Promise<Legalizacion> {
  const respuesta = await fetch("/api/v1/legalizaciones", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
    body: JSON.stringify({ ejercicio, fecha_legalizacion }),
  });
  return (await manejar(respuesta)) as Legalizacion;
}

export async function listarLegalizaciones(): Promise<ListaPaginada<Legalizacion>> {
  const respuesta = await fetch(`/api/v1/legalizaciones${paginar()}`, {
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as ListaPaginada<Legalizacion>;
}

export async function descargarLegalizacion(id: string): Promise<void> {
  await descargar(`/api/v1/legalizaciones/${id}/descarga`, `legalizacion-${id}.txt`);
}

export async function listarCajas(filtros: { page?: number; page_size?: number } = {}): Promise<ListaPaginada<Caja>> {
  const respuesta = await fetch(`/api/v1/cajas${paginar(filtros)}`, {
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as ListaPaginada<Caja>;
}

export async function obtenerCaja(id: string): Promise<DetalleCaja> {
  const respuesta = await fetch(`/api/v1/cajas/${id}`, {
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as DetalleCaja;
}

export async function crearCaja(body: {
  nombre: string;
  cuenta_570_id: number;
  tipo: string;
}): Promise<Caja> {
  const respuesta = await fetch("/api/v1/cajas", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
    body: JSON.stringify(body),
  });
  return (await manejar(respuesta)) as Caja;
}

export async function inactivarCaja(id: string): Promise<Caja> {
  const respuesta = await fetch(`/api/v1/cajas/${id}/inactivar`, {
    method: "POST",
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as Caja;
}

export async function registrarMovimiento(
  cajaId: string,
  body: {
    tipo: "entrada" | "salida";
    importe: string;
    fecha: string;
    concepto: string;
    contrapartida_cuenta_id: number;
  }
): Promise<Movimiento> {
  const respuesta = await fetch(`/api/v1/cajas/${cajaId}/movimientos`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
    body: JSON.stringify(body),
  });
  return (await manejar(respuesta)) as Movimiento;
}

export async function realizarArqueo(
  cajaId: string,
  body: { fecha: string; efectivo_contado: string; detalle?: string | null }
): Promise<Arqueo> {
  const respuesta = await fetch(`/api/v1/cajas/${cajaId}/arqueos`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
    body: JSON.stringify(body),
  });
  return (await manejar(respuesta)) as Arqueo;
}

export async function aprobarArqueo(arqueoId: string, asiento_ajuste_id?: string | null): Promise<Arqueo> {
  const respuesta = await fetch(`/api/v1/arqueos/${arqueoId}/aprobar`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
    body: JSON.stringify({ asiento_ajuste_id }),
  });
  return (await manejar(respuesta)) as Arqueo;
}

export async function archivarArqueo(arqueoId: string): Promise<Arqueo> {
  const respuesta = await fetch(`/api/v1/arqueos/${arqueoId}/archivar`, {
    method: "POST",
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as Arqueo;
}

export async function listarArqueos(
  filtros: { caja_id?: string; estado?: string; page?: number; page_size?: number } = {}
): Promise<ListaPaginada<Arqueo>> {
  const params = new URLSearchParams();
  if (filtros.caja_id) params.set("caja_id", filtros.caja_id);
  if (filtros.estado) params.set("estado", filtros.estado);
  if (filtros.page) params.set("page", String(filtros.page));
  if (filtros.page_size) params.set("page_size", String(filtros.page_size));
  const respuesta = await fetch(`/api/v1/arqueos?${params.toString()}`, {
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as ListaPaginada<Arqueo>;
}