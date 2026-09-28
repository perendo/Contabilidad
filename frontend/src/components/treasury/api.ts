import { cabecerasEmpresa } from "./empresa";
import { getToken } from "@/services/client";

export type RemesaEstado = "borrador" | "emitida" | "cobrada" | "devuelta";
export type RemesaFormato = "SEPA_DD" | "CSB_19_19";

export interface Recibo {
  id: string;
  recibo_num: string;
  tercero_id: string;
  iban: string;
  importe: string;
  fecha_cargo: string;
  estado: "pendiente" | "remesado" | "cobrado" | "devuelto";
  vencimiento_id: string;
  asiento_cobro_id: string | null;
}

export interface Remesa {
  id: string;
  empresa_id: number;
  ejercicio: number;
  numero_remesa: number;
  estado: RemesaEstado;
  formato: RemesaFormato;
  tipo_adeudo: "CORE" | "B2B";
  fecha_emision: string | null;
  fecha_cargo: string | null;
  importe_total: string;
  n_recibos?: number;
  recibos?: Recibo[];
}

export interface ListaRemesas {
  total: number;
  items: Remesa[];
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

export async function listarRemesas(
  filtros: { estado?: string; formato?: string; limit?: number; offset?: number } = {}
): Promise<ListaRemesas> {
  const params = new URLSearchParams();
  if (filtros.estado) params.set("estado", filtros.estado);
  if (filtros.formato) params.set("formato", filtros.formato);
  if (filtros.limit) params.set("limit", String(filtros.limit));
  if (filtros.offset) params.set("offset", String(filtros.offset));
  const respuesta = await fetch(`/api/v1/remesas?${params.toString()}`, {
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as ListaRemesas;
}

export async function obtenerRemesa(id: string): Promise<Remesa> {
  const respuesta = await fetch(`/api/v1/remesas/${id}`, {
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as Remesa;
}

export async function crearRemesa(
  body: { formato: RemesaFormato; tipo_adeudo: "CORE" | "B2B"; recibo_ids: string[] }
): Promise<Remesa> {
  const respuesta = await fetch("/api/v1/remesas", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
    body: JSON.stringify(body),
  });
  return (await manejar(respuesta)) as Remesa;
}

export async function emitirRemesa(id: string): Promise<Record<string, unknown>> {
  const respuesta = await fetch(`/api/v1/remesas/${id}/emitir`, {
    method: "POST",
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as Record<string, unknown>;
}

export async function cobrarRecibo(
  remesaId: string,
  reciboId: string
): Promise<{ recibo: Recibo; asiento_id: string; remesa_id: string }> {
  const respuesta = await fetch(
    `/api/v1/remesas/${remesaId}/recibos/${reciboId}/cobrar`,
    { method: "POST", headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() } }
  );
  return (await manejar(respuesta)) as {
    recibo: Recibo;
    asiento_id: string;
    remesa_id: string;
  };
}

export async function descargarFichero(remesaId: string): Promise<void> {
  const respuesta = await fetch(`/api/v1/remesas/${remesaId}/fichero`, {
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
  });
  if (!respuesta.ok) {
    throw new ApiError(respuesta.status, "No se pudo descargar el fichero");
  }
  const blob = await respuesta.blob();
  const url = URL.createObjectURL(blob);
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombreDescarga(respuesta, remesaId);
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  URL.revokeObjectURL(url);
}

function nombreDescarga(respuesta: Response, remesaId: string): string {
  const disposicion = respuesta.headers.get("content-disposition") ?? "";
  const coincidencia = /filename="?([^";]+)"?/.exec(disposicion);
  return coincidencia?.[1] ?? `remesa-${remesaId}`;
}

export function formatearImporte(importe: string): string {
  const numero = Number(importe);
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "EUR",
  }).format(numero);
}

export interface Devolucion {
  id: string;
  empresa_id: number;
  recibo_remesa_id: string;
  codigo: string;
  identificador_externo: string;
  motivo: string;
  fecha_registro: string;
  fecha_cargo_original: string;
  importe: string;
  importe_gastos: string;
  asiento_reversal_id: string | null;
  estado_reclamacion: "sin_reclamacion" | "reclamada" | "resuelta" | "desestimada";
  recibo?: {
    id: string | null;
    recibo_num: string | null;
    estado: string | null;
    asiento_cobro_id: string | null;
  };
  reclamaciones?: {
    id: string;
    estado: "abierta" | "en_curso" | "resuelta" | "desestimada";
    fecha_registro: string;
    observaciones: string | null;
  }[];
}

export interface ResultadoImport {
  procesadas: number;
  rechazadas: { motivo: string; code: string }[];
  total: number;
}

export async function listarDevoluciones(
  filtros: { codigo?: string; limit?: number; offset?: number } = {}
): Promise<{ items: Devolucion[]; total: number }> {
  const params = new URLSearchParams();
  if (filtros.codigo) params.set("codigo", filtros.codigo);
  if (filtros.limit) params.set("limit", String(filtros.limit));
  if (filtros.offset) params.set("offset", String(filtros.offset));
  const respuesta = await fetch(`/api/v1/devoluciones?${params.toString()}`, {
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as { items: Devolucion[]; total: number };
}

export async function obtenerDevolucion(id: string): Promise<Devolucion> {
  const respuesta = await fetch(`/api/v1/devoluciones/${id}`, {
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as Devolucion;
}

export async function importarFicheroR19(fichero: File): Promise<ResultadoImport> {
  const datos = new FormData();
  datos.append("file", fichero);
  const respuesta = await fetch("/api/v1/devoluciones/import", {
    method: "POST",
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
    body: datos,
  });
  return (await manejar(respuesta)) as ResultadoImport;
}

export async function importarDevolucionesJson(
  devoluciones: {
    recibo_id: string;
    codigo: string;
    motivo: string;
    importe: string;
    importe_gastos?: string;
    fecha_registro: string;
  }[]
): Promise<ResultadoImport> {
  const respuesta = await fetch("/api/v1/devoluciones/import", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
    body: JSON.stringify({ devoluciones }),
  });
  return (await manejar(respuesta)) as ResultadoImport;
}

export async function crearReclamacion(
  devolucionId: string,
  accion: string,
  observaciones?: string
): Promise<{ reclamacion_id: string; estado: string }> {
  const respuesta = await fetch(`/api/v1/devoluciones/${devolucionId}/reclamaciones`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
    body: JSON.stringify({ accion, observaciones }),
  });
  return (await manejar(respuesta)) as { reclamacion_id: string; estado: string };
}

// SPEC-021: Medios de pago y efectos

export type TipoEfecto = "CHEQUE" | "PAGARE" | "LETRA";
export type EstadoEfecto = "emitido" | "cobrado" | "impagado";
export type MedioCobro =
  | "TRANSFERENCIA"
  | "TARJETA"
  | "CHEQUE"
  | "PAGARE"
  | "LETRA"
  | "CAJA";

export interface EfectoItem {
  id: string;
  tipo_efecto: TipoEfecto;
  numero_documento: string;
  tercero_id: string;
  tercero_nombre: string | null;
  fecha_emision: string;
  fecha_vencimiento: string;
  importe: string;
  moneda: string;
  estado: EstadoEfecto;
  asiento_cobro_id: string | null;
  asiento_impago_id: string | null;
}

export interface ResumenCartera {
  total: number;
  items: EfectoItem[];
  por_estado: { estado: EstadoEfecto; total: number; importe: string }[];
  por_tipo: { tipo_efecto: TipoEfecto; total: number; importe: string }[];
}

export interface DetalleEfecto extends EfectoItem {
  notas: string | null;
  asientos: {
    asiento_cobro_id?: { id: string; tipo: string; concepto: string };
    asiento_impago_id?: { id: string; tipo: string; concepto: string };
  };
}

export interface CobroMedioItem {
  id: string;
  medio_cobro: MedioCobro;
  fecha_cobro: string;
  importe_total: string;
  importe_comision: string;
  importe_neto: string;
  cuenta_banco: string;
  vencimiento_id: string;
  asiento_cobro_id: string;
}

export async function listarEfectos(filtros: {
  estado?: EstadoEfecto;
  tipo_efecto?: TipoEfecto;
  tercero_id?: string;
  fecha_desde?: string;
  fecha_hasta?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<ResumenCartera> {
  const params = new URLSearchParams();
  if (filtros.estado) params.append("estado", filtros.estado);
  if (filtros.tipo_efecto) params.append("tipo_efecto", filtros.tipo_efecto);
  if (filtros.tercero_id) params.append("tercero_id", filtros.tercero_id);
  if (filtros.fecha_desde) params.append("fecha_desde", filtros.fecha_desde);
  if (filtros.fecha_hasta) params.append("fecha_hasta", filtros.fecha_hasta);
  if (filtros.limit) params.append("limit", String(filtros.limit));
  if (filtros.offset) params.append("offset", String(filtros.offset));
  const url = `/api/v1/efectos${params.toString() ? `?${params.toString()}` : ""}`;
  const respuesta = await fetch(url, { headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() } });
  return (await manejar(respuesta)) as ResumenCartera;
}

export async function obtenerEfecto(efectoId: string): Promise<DetalleEfecto> {
  const respuesta = await fetch(`/api/v1/efectos/${efectoId}`, {
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as DetalleEfecto;
}

export async function crearEfecto(payload: {
  tercero_id: string;
  tipo_efecto: TipoEfecto;
  numero_documento: string;
  fecha_emision: string;
  fecha_vencimiento: string;
  importe: string;
  moneda?: string;
  notas?: string;
}): Promise<{ id: string; estado: EstadoEfecto }> {
  const respuesta = await fetch("/api/v1/efectos", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
    body: JSON.stringify(payload),
  });
  return (await manejar(respuesta)) as { id: string; estado: EstadoEfecto };
}

export async function cobrarEfecto(
  efectoId: string,
  payload: { fecha_cobro: string; cuenta_banco?: string }
): Promise<{ id: string; estado: EstadoEfecto; asiento_cobro_id: string }> {
  const respuesta = await fetch(`/api/v1/efectos/${efectoId}/cobrar`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
    body: JSON.stringify(payload),
  });
  return (await manejar(respuesta)) as {
    id: string;
    estado: EstadoEfecto;
    asiento_cobro_id: string;
  };
}

export async function impagarEfecto(
  efectoId: string,
  payload: {
    fecha_impago: string;
    motivo?: string;
    gastos_devolucion?: string;
    cuenta_banco?: string;
  }
): Promise<{ id: string; estado: EstadoEfecto; asiento_impago_id: string }> {
  const respuesta = await fetch(`/api/v1/efectos/${efectoId}/impago`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
    body: JSON.stringify(payload),
  });
  return (await manejar(respuesta)) as {
    id: string;
    estado: EstadoEfecto;
    asiento_impago_id: string;
  };
}

export async function registrarCobroMedio(payload: {
  vencimiento_id: string;
  medio_cobro: MedioCobro;
  fecha_cobro: string;
  cuenta_banco?: string;
  importe_comision?: string;
  tipo_comision?: string;
  banco_codigo?: string;
  porcentaje?: string;
}): Promise<{
  id: string;
  medio_cobro: MedioCobro;
  importe_total: string;
  importe_comision: string;
  importe_neto: string;
  asiento_cobro_id: string;
  comision_id: string | null;
}> {
  const respuesta = await fetch("/api/v1/cobros-medio", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
    body: JSON.stringify(payload),
  });
  return (await manejar(respuesta)) as {
    id: string;
    medio_cobro: MedioCobro;
    importe_total: string;
    importe_comision: string;
    importe_neto: string;
    asiento_cobro_id: string;
    comision_id: string | null;
  };
}

export async function listarCobrosMedio(filtros: {
  medio_cobro?: MedioCobro;
  fecha_desde?: string;
  fecha_hasta?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<{ total: number; items: CobroMedioItem[] }> {
  const params = new URLSearchParams();
  if (filtros.medio_cobro) params.append("medio_cobro", filtros.medio_cobro);
  if (filtros.fecha_desde) params.append("fecha_desde", filtros.fecha_desde);
  if (filtros.fecha_hasta) params.append("fecha_hasta", filtros.fecha_hasta);
  if (filtros.limit) params.append("limit", String(filtros.limit));
  if (filtros.offset) params.append("offset", String(filtros.offset));
  const url = `/api/v1/cobros-medio${params.toString() ? `?${params.toString()}` : ""}`;
  const respuesta = await fetch(url, { headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() } });
  return (await manejar(respuesta)) as { total: number; items: CobroMedioItem[] };
}

// SPEC-022: Anticipos, fondos a cuenta y cesión de cobros

export type TipoAnticipo = "CLIENTE" | "PROVEEDOR";
export type EstadoAnticipo =
  | "pendiente"
  | "parcialmente_aplicado"
  | "totalmente_aplicado";
export type EstadoCesion = "activa" | "saldada" | "cancelada";
export type TipoComisionCesion = "IMPORTE_FIJO" | "PORCENTAJE";
export type MedioNotificacion = "EMAIL" | "CORREO" | "REGISTRO";
export type EstadoVencimiento =
  | "pendiente"
  | "parcial"
  | "remesado"
  | "cobrado"
  | "pagado"
  | "cedido";

export interface AnticipoItem {
  id: string;
  tercero_id: string;
  tercero_nombre: string;
  tipo: TipoAnticipo;
  fecha: string;
  importe: string;
  saldo_pendiente: string;
  estado: EstadoAnticipo;
  asiento_id: string | null;
}

export interface LiquidacionAnticipo {
  id: string;
  factura_id: string;
  fecha_aplicacion: string;
  importe_aplicado: string;
  asiento_id: string;
}

export interface DetalleAnticipo extends Omit<AnticipoItem, "asiento_id"> {
  cuenta_contable: string;
  asiento_id: string | null;
  notas: string | null;
  liquidaciones: LiquidacionAnticipo[];
}

export interface VencimientoItem {
  id: string;
  recibo_num: string;
  tercero_id: string;
  tipo: "cobro" | "pago";
  fecha_vencimiento: string;
  importe: string;
  acumulado: string;
  saldo_pendiente: string;
  estado: EstadoVencimiento;
}

export interface CesionItem {
  id: string;
  entidad_financiera: string;
  fecha_cesion: string;
  importe_total_cedido: string;
  comision: string;
  estado: EstadoCesion;
  n_vencimientos: number;
}

export interface NotificacionCesion {
  id: string;
  cliente_id: string;
  fecha_notificacion: string;
  medio: MedioNotificacion;
  estado: string;
}

export interface DetalleCesion extends CesionItem {
  tipo_comision: TipoComisionCesion;
  importe_neto_recibido: string;
  asiento_id: string;
  notas: string | null;
  vencimientos: {
    vencimiento_id: string;
    recibo_num: string;
    tercero_id: string;
    tercero_nombre: string;
    importe: string;
    estado: EstadoVencimiento;
  }[];
  notificaciones: NotificacionCesion[];
}

export async function listarAnticipos(filtros: {
  tipo?: TipoAnticipo;
  estado?: EstadoAnticipo;
  tercero_id?: string;
  fecha_desde?: string;
  fecha_hasta?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<{ total: number; items: AnticipoItem[] }> {
  const params = new URLSearchParams();
  if (filtros.tipo) params.append("tipo", filtros.tipo);
  if (filtros.estado) params.append("estado", filtros.estado);
  if (filtros.tercero_id) params.append("tercero_id", filtros.tercero_id);
  if (filtros.fecha_desde) params.append("fecha_desde", filtros.fecha_desde);
  if (filtros.fecha_hasta) params.append("fecha_hasta", filtros.fecha_hasta);
  if (filtros.limit) params.append("limit", String(filtros.limit));
  if (filtros.offset) params.append("offset", String(filtros.offset));
  const url = `/api/v1/anticipos${params.toString() ? `?${params.toString()}` : ""}`;
  const respuesta = await fetch(url, { headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() } });
  return (await manejar(respuesta)) as { total: number; items: AnticipoItem[] };
}

export async function obtenerAnticipo(id: string): Promise<DetalleAnticipo> {
  const respuesta = await fetch(`/api/v1/anticipos/${id}`, {
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as DetalleAnticipo;
}

export async function crearAnticipo(payload: {
  tercero_id: string;
  tipo: TipoAnticipo;
  fecha: string;
  importe: string;
  concepto: string;
  cuenta_contable?: string;
  notas?: string;
}): Promise<{ id: string; tipo: TipoAnticipo; importe: string; saldo_pendiente: string; asiento_id: string }> {
  const respuesta = await fetch("/api/v1/anticipos", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
    body: JSON.stringify(payload),
  });
  return (await manejar(respuesta)) as {
    id: string;
    tipo: TipoAnticipo;
    importe: string;
    saldo_pendiente: string;
    asiento_id: string;
  };
}

export async function liquidarAnticipo(
  id: string,
  payload: {
    aplicaciones: { factura_id: string; importe_aplicado: string }[];
    fecha_aplicacion: string;
  }
): Promise<{ saldo_pendiente: string; liquidaciones_creadas: number }> {
  const respuesta = await fetch(`/api/v1/anticipos/${id}/liquidar`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
    body: JSON.stringify(payload),
  });
  return (await manejar(respuesta)) as {
    saldo_pendiente: string;
    liquidaciones_creadas: number;
  };
}

export async function listarVencimientos(filtros: {
  estado?: EstadoVencimiento;
  limit?: number;
  offset?: number;
} = {}): Promise<{ items: VencimientoItem[]; total: number }> {
  const params = new URLSearchParams();
  if (filtros.estado) params.append("estado", filtros.estado);
  if (filtros.limit) params.append("limit", String(filtros.limit));
  if (filtros.offset) params.append("offset", String(filtros.offset));
  const url = `/api/v1/vencimientos${params.toString() ? `?${params.toString()}` : ""}`;
  const respuesta = await fetch(url, { headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() } });
  return (await manejar(respuesta)) as { items: VencimientoItem[]; total: number };
}

export async function listarCesiones(filtros: {
  estado?: EstadoCesion;
  entidad_financiera?: string;
  fecha_desde?: string;
  fecha_hasta?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<{ total: number; items: CesionItem[] }> {
  const params = new URLSearchParams();
  if (filtros.estado) params.append("estado", filtros.estado);
  if (filtros.entidad_financiera) params.append("entidad_financiera", filtros.entidad_financiera);
  if (filtros.fecha_desde) params.append("fecha_desde", filtros.fecha_desde);
  if (filtros.fecha_hasta) params.append("fecha_hasta", filtros.fecha_hasta);
  if (filtros.limit) params.append("limit", String(filtros.limit));
  if (filtros.offset) params.append("offset", String(filtros.offset));
  const url = `/api/v1/cesiones${params.toString() ? `?${params.toString()}` : ""}`;
  const respuesta = await fetch(url, { headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() } });
  return (await manejar(respuesta)) as { total: number; items: CesionItem[] };
}

export async function obtenerCesion(id: string): Promise<DetalleCesion> {
  const respuesta = await fetch(`/api/v1/cesiones/${id}`, {
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as DetalleCesion;
}

export async function crearCesion(payload: {
  entidad_financiera: string;
  fecha_cesion: string;
  vencimiento_ids: string[];
  comision: string;
  tipo_comision: TipoComisionCesion;
  notas?: string;
}): Promise<{
  id: string;
  entidad_financiera: string;
  importe_total_cedido: string;
  comision: string;
  importe_neto_recibido: string;
  asiento_id: string;
  n_vencimientos: number;
}> {
  const respuesta = await fetch("/api/v1/cesiones", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
    body: JSON.stringify(payload),
  });
  return (await manejar(respuesta)) as {
    id: string;
    entidad_financiera: string;
    importe_total_cedido: string;
    comision: string;
    importe_neto_recibido: string;
    asiento_id: string;
    n_vencimientos: number;
  };
}

export async function notificarCesion(
  id: string,
  payload: { cliente_id: string; medio: MedioNotificacion; fecha_notificacion: string; notas?: string }
): Promise<{ notificacion_id: string; estado: string }> {
  const respuesta = await fetch(`/api/v1/cesiones/${id}/notificar`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
    body: JSON.stringify(payload),
  });
  return (await manejar(respuesta)) as { notificacion_id: string; estado: string };
}

export async function saldarCesion(
  id: string,
  payload: { fecha_saldado: string }
): Promise<{ estado: EstadoCesion }> {
  const respuesta = await fetch(`/api/v1/cesiones/${id}/saldar`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
    body: JSON.stringify(payload),
  });
  return (await manejar(respuesta)) as { estado: EstadoCesion };
}