import { get, getToken, post } from "@/services/client";
import { cabecerasEmpresa } from "@/components/treasury/empresa";

import { ApiError } from "@/components/treasury/api";

export { ApiError };

export type TipoPresupuesto = "gasto" | "ingreso";
export type EstadoPeriodo = "abierto" | "cerrado" | "sin_periodo";

export interface LineaPresupuesto {
  id: string;
  ejercicio: number;
  cuenta_id: number;
  codigo_cuenta: string;
  nombre_cuenta: string;
  centro_coste_id: string | null;
  nombre_centro: string | null;
  importe: string;
  tipo: TipoPresupuesto;
  periodo_id: string | null;
}

export interface ListadoPresupuestos {
  items: LineaPresupuesto[];
  total: number;
}

export interface Desviacion {
  cuenta_id: number;
  codigo_cuenta: string;
  nombre_cuenta: string;
  centro_coste_id: string | null;
  nombre_centro: string | null;
  importe_presupuestado: string;
  importe_real: string;
  desviacion_absoluta: string;
  desviacion_relativa: string | null;
  sin_presupuesto: boolean;
}

export interface Seguimiento {
  ejercicio: number;
  desde: string;
  hasta: string;
  items: Desviacion[];
  total: number;
}

export interface Periodo {
  periodo_id: string | null;
  ejercicio: number;
  numero_periodo: number | null;
  estado: EstadoPeriodo;
  fecha_inicio: string | null;
  fecha_fin: string | null;
  fecha_cierre: string | null;
  cerrado_por: string | null;
  desviaciones_registradas: number;
}

export interface ListadoPeriodos {
  items: Periodo[];
  total: number;
}

export interface SubtotalCentro {
  centro_coste_id: string | null;
  nombre_centro: string;
  importe_presupuestado: string;
  importe_real: string;
  desviacion_absoluta: string;
  lineas: number;
}

export interface InformeDesviacion {
  ejercicio: number;
  origen: "calculo" | "snapshot";
  mes: number | null;
  total_presupuestado: string;
  total_real: string;
  total_desviacion: string;
  cuadra: boolean;
  lineas_sin_presupuesto: number;
  centros: SubtotalCentro[];
  items: Desviacion[];
  total: number;
}

export interface ResultadoCierre {
  periodo_id: string;
  ejercicio: number;
  numero_periodo: number;
  estado: EstadoPeriodo;
  desviaciones_registradas: number;
  fecha_cierre: string | null;
  cerrado_por: string | null;
}

export interface ResultadoImportacion {
  ejercicio: number;
  importadas: number;
  errores: { fila: number; motivo: string }[];
}

export interface CuentaOption {
  account_id: number;
  codigo: string;
  nombre: string;
}

export interface NodoCuenta {
  id: number;
  code: string;
  name: string;
  level: number;
  is_selectable: boolean;
  is_active: boolean;
  parent_id: number | null;
  children: NodoCuenta[];
}

function qs(params: Record<string, string | number | undefined>): string {
  const entrada = new URLSearchParams();
  for (const [clave, valor] of Object.entries(params)) {
    if (valor !== undefined && valor !== "") entrada.append(clave, String(valor));
  }
  const texto = entrada.toString();
  return texto ? `?${texto}` : "";
}

export function listarPresupuestos(
  params: Record<string, string | number | undefined> = {}
): Promise<ListadoPresupuestos> {
  return get<ListadoPresupuestos>(`/api/v1/presupuestos${qs(params)}`);
}

export function guardarPresupuesto(body: {
  ejercicio: number;
  cuenta_id: number;
  centro_coste_id?: string | null;
  importe: string;
  tipo?: TipoPresupuesto;
  observaciones?: string;
}): Promise<LineaPresupuesto> {
  return post<LineaPresupuesto>("/api/v1/presupuestos", body);
}

export function seguimiento(
  params: Record<string, string | number | undefined>
): Promise<Seguimiento> {
  return get<Seguimiento>(`/api/v1/presupuestos/seguimiento${qs(params)}`);
}

export function periodoActual(ejercicio: number): Promise<Periodo> {
  return get<Periodo>(`/api/v1/presupuestos/seguimiento/periodo?ejercicio=${ejercicio}`);
}

export function listarPeriodos(ejercicio?: number): Promise<ListadoPeriodos> {
  return get<ListadoPeriodos>(`/api/v1/presupuestos/periodos${qs({ ejercicio })}`);
}

export function crearPeriodo(body: {
  ejercicio: number;
  fecha_inicio: string;
  fecha_fin: string;
  notas?: string;
}): Promise<Periodo & { periodo_id: string }> {
  return post("/api/v1/presupuestos/periodos", body);
}

export function informeDesviacion(
  params: Record<string, string | number | undefined>
): Promise<InformeDesviacion> {
  return get<InformeDesviacion>(`/api/v1/presupuestos/informes/desviacion${qs(params)}`);
}

export function cerrarPeriodo(body: {
  ejercicio: number;
  periodo_id: string;
}): Promise<ResultadoCierre> {
  return post<ResultadoCierre>("/api/v1/presupuestos/informes/cerrar", body);
}

export function snapshotPeriodo(
  periodoId: string
): Promise<{ periodo_id: string; items: Desviacion[]; total: number }> {
  return get(`/api/v1/presupuestos/seguimiento/snapshot${qs({ periodo_id: periodoId })}`);
}

/** Cuentas presupuestables (grupo 6 y 7) del plan de la empresa activa. */
export async function cuentasPresupuestables(): Promise<CuentaOption[]> {
  const cuerpo = await get<{ nodos: NodoCuenta[] }>("/api/v1/accounts/tree");
  const salida: CuentaOption[] = [];
  const recorrer = (nodos: NodoCuenta[]) => {
    for (const nodo of nodos) {
      if (
        nodo.is_selectable &&
        nodo.is_active &&
        (nodo.code.startsWith("6") || nodo.code.startsWith("7"))
      ) {
        salida.push({
          account_id: nodo.id,
          codigo: nodo.code,
          nombre: nodo.name,
        });
      }
      recorrer(nodo.children ?? []);
    }
  };
  recorrer(cuerpo.nodos ?? []);
  return salida.sort((a, b) => a.codigo.localeCompare(b.codigo));
}

export async function importarPresupuesto(
  file: File
): Promise<ResultadoImportacion> {
  const datos = new FormData();
  datos.append("file", file);
  const cabeceras: Record<string, string> = {};
  const token = getToken();
  if (token) cabeceras["Authorization"] = `Bearer ${token}`;
  Object.assign(cabeceras, cabecerasEmpresa());
  const respuesta = await fetch("/api/v1/presupuestos/importar", {
    method: "POST",
    headers: cabeceras,
    body: datos,
  });
  const cuerpo = (await respuesta.json().catch(() => ({}))) as {
    detail?: string | { detail?: string; code?: string };
  };
  if (!respuesta.ok) {
    const detalle = cuerpo.detail;
    const mensaje =
      typeof detalle === "string"
        ? detalle
        : detalle?.detail ?? `${respuesta.status} ${respuesta.statusText}`;
    const code = typeof detalle === "object" ? detalle.code : undefined;
    throw new ApiError(respuesta.status, mensaje, code);
  }
  return cuerpo as unknown as ResultadoImportacion;
}

export function formatearImporte(importe: string): string {
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 4,
    maximumFractionDigits: 4,
  }).format(Number(importe));
}

export function formatearPorcentaje(ratio: string | null): string {
  if (ratio === null) return "—";
  return `${new Intl.NumberFormat("es-ES", {
    style: "percent",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(ratio))}`;
}
