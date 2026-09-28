import { cabecerasEmpresa } from "../treasury/empresa";

export type MetodoAmortizacion = "lineal" | "regresivo";
export type EstadoActivo = "en_uso" | "dado_de_baja";
export type TipoBaja = "venta" | "retirada";

export interface FilaPlan {
  ejercicio: number;
  periodo: number;
  cuota: string;
  acumulado: string;
  estado?: string;
}

export interface Activo {
  id: string;
  numero_activo: string;
  cuenta_id: number;
  descripcion: string;
  fecha_alta: string;
  coste_amortizable: string;
  vida_util: number;
  metodo: MetodoAmortizacion;
  porcentaje_regresivo: string | null;
  estado: EstadoActivo;
  cuenta_gasto_id: number;
  cuenta_acumulada_id: number;
  fecha_baja: string | null;
  amortizado_acumulado?: string;
  plan?: FilaPlan[];
}

export interface ListaActivos {
  total: number;
  items: Activo[];
}

export interface DatosPlan {
  numero_activo: string;
  cuenta_id: number;
  descripcion: string;
  fecha_alta: string;
  coste_amortizable: string;
  vida_util: number;
  metodo: MetodoAmortizacion;
  porcentaje_regresivo?: string | null;
  cuenta_gasto_id?: number | null;
  cuenta_acumulada_id?: number | null;
}

export interface ResultadoPlan {
  plan: FilaPlan[];
  total_amortizable: string;
}

export interface Generada {
  id: string;
  activo_id: string;
  ejercicio: number;
  periodo: number;
  asiento_id: string;
  cuota: string;
  reabierta: boolean;
  reapertura_de: string | null;
  created_at: string;
}

export interface Omision {
  activo_id: string;
  motivo: string;
  detalle: string;
}

export interface ResultadoGenerar {
  generados: Generada[];
  omitidos: Omision[];
  n: number;
}

export interface ResultadoReabrir {
  amortizacion_id: string;
  asiento_original_id: string;
  reversal_asiento_id: string;
  numero_reversal: number;
  reabierta: boolean;
  cuota: string;
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

export async function listarActivos(
  filtros: {
    estado?: string;
    cuenta_id?: number;
    ejercicio_alta?: number;
    page?: number;
    page_size?: number;
  } = {}
): Promise<ListaActivos> {
  const params = new URLSearchParams();
  if (filtros.estado) params.set("estado", filtros.estado);
  if (filtros.cuenta_id) params.set("cuenta_id", String(filtros.cuenta_id));
  if (filtros.ejercicio_alta) params.set("ejercicio_alta", String(filtros.ejercicio_alta));
  if (filtros.page) params.set("page", String(filtros.page));
  if (filtros.page_size) params.set("page_size", String(filtros.page_size));
  const respuesta = await fetch(`/api/v1/activos?${params.toString()}`, {
    headers: { ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as ListaActivos;
}

export async function obtenerActivo(id: string): Promise<Activo> {
  const respuesta = await fetch(`/api/v1/activos/${id}`, {
    headers: { ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as Activo;
}

export async function crearActivo(datos: DatosPlan): Promise<Activo> {
  const respuesta = await fetch(`/api/v1/activos`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...cabecerasEmpresa() },
    body: JSON.stringify(datos),
  });
  return (await manejar(respuesta)) as Activo;
}

export async function editarActivo(
  id: string,
  datos: Partial<Pick<DatosPlan, "descripcion" | "vida_util" | "coste_amortizable" | "metodo" | "porcentaje_regresivo" | "cuenta_gasto_id" | "cuenta_acumulada_id">>
): Promise<Activo> {
  const respuesta = await fetch(`/api/v1/activos/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...cabecerasEmpresa() },
    body: JSON.stringify(datos),
  });
  return (await manejar(respuesta)) as Activo;
}

export async function calcularPlan(datos: DatosPlan): Promise<ResultadoPlan> {
  const respuesta = await fetch(`/api/v1/activos/plan/calcular`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...cabecerasEmpresa() },
    body: JSON.stringify(datos),
  });
  return (await manejar(respuesta)) as ResultadoPlan;
}

export async function darDeBaja(
  id: string,
  datos: { fecha_baja: string; precio_venta?: string; tipo?: TipoBaja }
) {
  const respuesta = await fetch(`/api/v1/activos/${id}/baja`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...cabecerasEmpresa() },
    body: JSON.stringify(datos),
  });
  return (await manejar(respuesta)) as {
    id: string;
    activo_id: string;
    fecha_baja: string;
    tipo: TipoBaja;
    amortizacion_hasta_baja: string;
    amortizacion_acumulada: string;
    valor_neto_contable: string;
    resultado: string;
    asiento_id: string;
  };
}

export async function generarAmortizacion(
  ejercicio: number,
  periodo: number
): Promise<ResultadoGenerar> {
  const respuesta = await fetch(`/api/v1/amortizaciones/generar`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...cabecerasEmpresa() },
    body: JSON.stringify({ ejercicio, periodo }),
  });
  return (await manejar(respuesta)) as ResultadoGenerar;
}

export async function reabrirAmortizacion(
  generadaId: string,
  motivo: string
): Promise<ResultadoReabrir> {
  const respuesta = await fetch(`/api/v1/amortizaciones/${generadaId}/reabrir`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...cabecerasEmpresa() },
    body: JSON.stringify({ motivo }),
  });
  return (await manejar(respuesta)) as ResultadoReabrir;
}

export async function listarAmortizaciones(
  filtros: {
    activo_id?: string;
    ejercicio?: number;
    periodo?: number;
    page?: number;
    page_size?: number;
  } = {}
) {
  const params = new URLSearchParams();
  if (filtros.activo_id) params.set("activo_id", filtros.activo_id);
  if (filtros.ejercicio) params.set("ejercicio", String(filtros.ejercicio));
  if (filtros.periodo) params.set("periodo", String(filtros.periodo));
  if (filtros.page) params.set("page", String(filtros.page));
  if (filtros.page_size) params.set("page_size", String(filtros.page_size));
  const respuesta = await fetch(`/api/v1/amortizaciones?${params.toString()}`, {
    headers: { ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as { total: number; items: Generada[] };
}