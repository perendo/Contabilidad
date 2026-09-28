import { ApiError } from "@/components/treasury/api";
import { get, post } from "@/services/client";

export { ApiError };

export type Granularidad = "dia" | "semana" | "mes";
export type EstadoPrevision = "borrador" | "generada" | "anulada";
export type TipoMovimiento = "cobro" | "pago";
export type Frecuencia = "unico" | "semanal" | "mensual" | "anual";
export type Origen = "vencimiento" | "remesa_cobro" | "pago_recurrente" | "cobro_estimado";
export type EstadoAlerta = "abierta" | "atendida" | "ignorada";
export type AccionSugerida = "reprogramar_pago" | "incluir_ingreso";
export type Bloque = "operativa" | "inversion" | "financiacion";

export interface MovimientoManual {
  tipo: TipoMovimiento;
  importe: string;
  fecha_prevista?: string | null;
  frecuencia?: Frecuencia;
  concepto?: string | null;
}

export interface Prevision {
  id: string;
  numero_prevision: number;
  fecha_generacion: string;
  desde_fecha: string;
  hasta_fecha: string;
  granularidad: Granularidad;
  saldo_inicial: string;
  saldo_final: string;
  origen_saldo_inicial: string | null;
  estado: EstadoPrevision;
  creado_por: string | null;
}

export interface ListadoPrevisiones {
  items: Prevision[];
  total: number;
  page: number;
}

export interface Bucket {
  fecha: string;
  cobros: string;
  pagos: string;
  neto: string;
  saldo_acumulado: string;
  alerta: boolean;
}

export interface Excluido {
  origen: Origen;
  tipo: TipoMovimiento;
  importe: string;
  fecha_prevista: string | null;
  motivo: string;
  concepto: string | null;
  vencimiento_id: string | null;
}

export interface MovimientoDetalle {
  id: string;
  origen: Origen;
  tipo: TipoMovimiento;
  importe: string;
  fecha_prevista: string | null;
  frecuencia: Frecuencia;
  concepto: string | null;
  incluido: boolean;
}

export interface Alerta {
  id: string;
  fecha: string;
  saldo_proyectado: string;
  importe_deficit: string;
  estado: EstadoAlerta;
  accion_sugerida: AccionSugerida;
  movimiento_origen_id: string | null;
}

export interface ResultadoGenerar extends Prevision {
  n_movimientos: number;
  n_alertas: number;
  excluidos: Excluido[];
  buckets: Bucket[];
}

export interface DetallePrevision extends Prevision {
  buckets: Bucket[];
  alertas: Alerta[];
  movimientos: MovimientoDetalle[];
  excluidos: Excluido[];
}

export interface ListadoAlertas {
  items: Alerta[];
  total: number;
  page: number;
}

export interface ResultadoAlerta {
  alerta_id: string;
  estado: EstadoAlerta;
  movimiento_id: string | null;
}

export interface LineaEFE {
  cuenta_id: number;
  codigo_cuenta: string;
  importe: string;
  override_usuario: boolean;
}

export interface BloqueEFE {
  total: string;
  items: LineaEFE[];
}

export interface InformeEFE {
  ejercicio: number;
  saldo_inicial: string;
  variacion_neta: string;
  saldo_final: string;
  cuadre: boolean;
  sin_conciliar: boolean;
  saldo_conciliacion: string | null;
  formulado: boolean;
  informe_id: string | null;
  bloques: Record<Bloque, BloqueEFE>;
}

export interface ResultadoFormularEFE {
  informe_id: string;
  estado: "formulado";
  cuadre: boolean;
  sin_conciliar: boolean;
  saldo_inicial: string;
  variacion_neta: string;
  saldo_final: string;
  totales: Record<Bloque, string>;
}

const BASE = "/api/v1/tesoreria";

function qs(params: Record<string, string | number | undefined>): string {
  const entrada = new URLSearchParams();
  for (const [clave, valor] of Object.entries(params)) {
    if (valor !== undefined && valor !== "") entrada.append(clave, String(valor));
  }
  const texto = entrada.toString();
  return texto ? `?${texto}` : "";
}

export function listarPrevisiones(
  params: Record<string, string | number | undefined> = {}
): Promise<ListadoPrevisiones> {
  return get<ListadoPrevisiones>(`${BASE}/previsiones${qs(params)}`);
}

export function generarPrevision(body: {
  desde_fecha: string;
  hasta_fecha: string;
  granularidad: Granularidad;
  movimientos_manuales?: MovimientoManual[];
}): Promise<ResultadoGenerar> {
  return post<ResultadoGenerar>(`${BASE}/previsiones`, body);
}

export function obtenerPrevision(id: string): Promise<DetallePrevision> {
  return get<DetallePrevision>(`${BASE}/previsiones/${id}`);
}

export function regenerarPrevision(
  id: string,
  body: { hasta_fecha?: string | null; granularidad?: Granularidad | null }
): Promise<ResultadoGenerar> {
  return post<ResultadoGenerar>(`${BASE}/previsiones/${id}/regenerar`, body);
}

export function anadirMovimiento(
  id: string,
  body: MovimientoManual & { fecha_prevista: string }
): Promise<MovimientoDetalle> {
  return post<MovimientoDetalle>(`${BASE}/previsiones/${id}/movimientos`, body);
}

export function listarAlertas(
  params: Record<string, string | number | undefined> = {}
): Promise<ListadoAlertas> {
  return get<ListadoAlertas>(`${BASE}/alertas${qs(params)}`);
}

export function atenderAlerta(
  id: string,
  body: {
    accion: AccionSugerida;
    movimiento_id?: string | null;
    nueva_fecha?: string | null;
    importe?: string | null;
  }
): Promise<ResultadoAlerta> {
  return post<ResultadoAlerta>(`${BASE}/alertas/${id}/atender`, body);
}

export function ignorarAlerta(id: string): Promise<ResultadoAlerta> {
  return post<ResultadoAlerta>(`${BASE}/alertas/${id}/ignorar`, {});
}

export function obtenerEFE(ejercicio: number): Promise<InformeEFE> {
  return get<InformeEFE>(`${BASE}/efe?ejercicio=${ejercicio}`);
}

export function formularEFE(
  ejercicio: number,
  clasificaciones: { cuenta_id: number; bloque: Bloque }[] = []
): Promise<ResultadoFormularEFE> {
  return post<ResultadoFormularEFE>(`${BASE}/efe/formular`, { ejercicio, clasificaciones });
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

export function esNegativo(importe: string): boolean {
  return Number(importe) < 0;
}

export const MOTIVOS_EXCLUSION: Record<string, string> = {
  vencido: "Vencido anterior al inicio de la previsión",
  cobrado: "Ya cobrado, remesado o devuelto",
  anulado: "Anulado",
  sin_fecha: "Sin fecha prevista: hay que datarlo",
};
