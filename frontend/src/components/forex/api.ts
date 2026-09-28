import { cabecerasEmpresa } from "../treasury/empresa";

export interface Divisa {
  id: string;
  codigo_iso: string;
  es_funcional: boolean;
  activa: boolean;
}

export interface ListaDivisas {
  funcional: string;
  items: Divisa[];
}

export interface TipoCambio {
  id: string;
  divisa_id: string;
  divisa: string;
  fecha: string;
  ratio: string;
  usos_posteados: number;
  sellado: boolean;
}

export interface ListaTipos {
  items: TipoCambio[];
  total: number;
  page: number;
  page_size: number;
}

export interface LineaDivisaInput {
  cuenta_id: number;
  debe_divisa: string;
  haber_divisa: string;
}

export interface AsientoDivisa {
  id: string;
  asiento_id: string;
  numero_asiento: number;
  fecha: string;
  divisa_id: string;
  divisa: string;
  concepto: string;
  importe_total_divisa: string;
  importe_total_funcional: string;
  ratio: string;
  tipo_cambio_id: string;
  sellado: boolean;
  usos_posteados: number;
  n_lineas: number;
  linea_redondeo: { cuenta: string; importe: string } | null;
}

export interface DetalleAsientoDivisa extends AsientoDivisa {
  total_divisa: string;
  total_funcional: string;
  lineas: {
    linea_id: string;
    cuenta: string;
    cuenta_id: number | null;
    debe: string;
    haber: string;
    debe_funcional: string;
    haber_funcional: string;
    debe_divisa: string;
    haber_divisa: string;
    importe_divisa: string;
    importe_funcional: string;
    es_linea_redondeo: boolean;
  }[];
}

export interface ValoracionItem {
  cuenta: string;
  cuenta_id: number;
  divisa_id: string;
  divisa: string;
  saldo_divisa: string;
  saldo_funcional_previo: string;
  valoracion: string;
  diferencia: string;
  tipo: "ganancia" | "perdida";
}

export interface ValoracionResultado {
  n: number;
  asiento_id: string | null;
  valoraciones: ValoracionItem[];
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
    throw new ApiError(
      respuesta.status,
      typeof detalle === "string" ? detalle : `${respuesta.status} ${respuesta.statusText}`
    );
  }
  return cuerpo;
}

export async function listarDivisas(): Promise<ListaDivisas> {
  const respuesta = await fetch("/api/v1/divisas", {
    headers: { ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as ListaDivisas;
}

export async function crearDivisa(codigoIso: string): Promise<Divisa> {
  const respuesta = await fetch("/api/v1/divisas", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...cabecerasEmpresa() },
    body: JSON.stringify({ codigo_iso: codigoIso }),
  });
  return (await manejar(respuesta)) as Divisa;
}

export async function listarTipos(
  filtros: {
    divisa_id?: string;
    fecha_gte?: string;
    fecha_lte?: string;
    sellado?: boolean;
  } = {}
): Promise<ListaTipos> {
  const params = new URLSearchParams();
  if (filtros.divisa_id) params.set("divisa_id", filtros.divisa_id);
  if (filtros.fecha_gte) params.set("fecha_gte", filtros.fecha_gte);
  if (filtros.fecha_lte) params.set("fecha_lte", filtros.fecha_lte);
  if (filtros.sellado !== undefined) params.set("sellado", String(filtros.sellado));
  const respuesta = await fetch(`/api/v1/tipos-cambio?${params.toString()}`, {
    headers: { ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as ListaTipos;
}

export async function crearTipo(
  divisaId: string,
  fecha: string,
  ratio: string
): Promise<TipoCambio> {
  const respuesta = await fetch("/api/v1/tipos-cambio", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...cabecerasEmpresa() },
    body: JSON.stringify({ divisa_id: divisaId, fecha, ratio }),
  });
  return (await manejar(respuesta)) as TipoCambio;
}

export async function corregirTipo(
  tipoId: string,
  ratio: string,
  motivo: string
): Promise<TipoCambio> {
  const respuesta = await fetch(`/api/v1/tipos-cambio/${tipoId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...cabecerasEmpresa() },
    body: JSON.stringify({ ratio, motivo }),
  });
  return (await manejar(respuesta)) as TipoCambio;
}

export async function historialPorAsiento(asientoId: string): Promise<ListaTipos> {
  const respuesta = await fetch(
    `/api/v1/tipos-cambio/historial?asiento_id=${asientoId}`,
    { headers: { ...cabecerasEmpresa() } }
  );
  return (await manejar(respuesta)) as ListaTipos;
}

export async function crearAsientoDivisa(body: {
  fecha: string;
  divisa_id: string;
  concepto?: string;
  lineas: LineaDivisaInput[];
  tipo_cambio_id?: string;
  tipo_ratio_explicito?: { ratio: string };
}): Promise<AsientoDivisa> {
  const respuesta = await fetch("/api/v1/asientos-divisa", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...cabecerasEmpresa() },
    body: JSON.stringify(body),
  });
  return (await manejar(respuesta)) as AsientoDivisa;
}

export async function detalleAsientoDivisa(asientoId: string): Promise<DetalleAsientoDivisa> {
  const respuesta = await fetch(`/api/v1/asientos-divisa/${asientoId}`, {
    headers: { ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as DetalleAsientoDivisa;
}

export async function crearValoracion(
  ejercicio: number,
  fechaValoracion: string
): Promise<ValoracionResultado> {
  const respuesta = await fetch("/api/v1/valoraciones", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...cabecerasEmpresa() },
    body: JSON.stringify({ ejercicio, fecha_valoracion: fechaValoracion }),
  });
  return (await manejar(respuesta)) as ValoracionResultado;
}

export async function listarDiferenciasCambio(
  filtros: { ejercicio?: number; divisa_id?: string } = {}
): Promise<{
  total: number;
  items: (ValoracionItem & {
    id: string;
    fecha_valoracion: string;
    estado: string;
    asiento_id: string | null;
  })[];
}> {
  const params = new URLSearchParams();
  if (filtros.ejercicio) params.set("ejercicio", String(filtros.ejercicio));
  if (filtros.divisa_id) params.set("divisa_id", filtros.divisa_id);
  const respuesta = await fetch(`/api/v1/diferencias-cambio?${params.toString()}`, {
    headers: { ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as {
    total: number;
    items: (ValoracionItem & {
      id: string;
      fecha_valoracion: string;
      estado: string;
      asiento_id: string | null;
    })[];
  };
}

export function formatearImporte(importe: string): string {
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "EUR",
  }).format(Number(importe));
}