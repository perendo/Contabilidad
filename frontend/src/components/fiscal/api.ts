import { get, patch, post, remove, requestBlob } from "@/services/client";

export { ApiError } from "@/components/treasury/api";

export type EstadoCalculo = "borrador" | "calculado" | "contabilizado";
export type TipoAjuste =
  | "AJUSTE_POSITIVO"
  | "AJUSTE_NEGATIVO"
  | "DEDUCCION"
  | "BONIFICACION";

export interface AjusteExtracontable {
  id: string;
  tipo: TipoAjuste;
  descripcion: string;
  referencia_normativa: string | null;
  importe: string;
}

export interface AjusteInput {
  tipo: TipoAjuste;
  descripcion: string;
  referencia_normativa?: string | null;
  importe: string;
}

export interface CalculoResumen {
  id: string;
  ejercicio: number;
  resultado_contable: string;
  ajustes_positivos: string;
  ajustes_negativos: string;
  base_imponible: string;
  tipo_impositivo: string;
  cuota_integra: string;
  deducciones: string;
  bonificaciones?: string;
  cuota_liquida: string;
  pagos_a_cuenta: string;
  cuota_diferencial: string;
  provisional: boolean;
  estado: EstadoCalculo;
  asiento_id?: string | null;
}

export interface DetalleCalculo extends CalculoResumen {
  ajustes: AjusteExtracontable[];
  notas: string | null;
  asiento_id: string | null;
}

export interface ListaCalculos {
  items: CalculoResumen[];
  total: number;
}

export interface Modelo200 {
  id: string;
  calculo_is_id: string;
  fecha_generacion: string;
  hash_contenido: string;
  ejercicio?: number;
  nombre_fichero?: string | null;
  content_type?: string | null;
}

export interface ListaModelos200 {
  items: Modelo200[];
  total: number;
}

export interface ConfiguracionFiscal {
  tipo_is: string;
  fecha_vigencia_desde: string;
  fecha_vigencia_hasta?: string | null;
}

export interface FiltrosCalculos {
  ejercicio?: number;
  provisional?: boolean;
  estado?: EstadoCalculo;
  limit?: number;
  offset?: number;
  page?: number;
  page_size?: number;
}

export interface FiltrosModelos200 {
  ejercicio?: number;
  limit?: number;
  offset?: number;
}

function query(params: Record<string, string | number | boolean | undefined>): string {
  const buscador = new URLSearchParams();
  Object.entries(params).forEach(([clave, valor]) => {
    if (valor !== undefined && valor !== "") buscador.set(clave, String(valor));
  });
  const resultado = buscador.toString();
  return resultado ? `?${resultado}` : "";
}

export function listarCalculos(filtros: FiltrosCalculos = {}): Promise<ListaCalculos> {
  return get<ListaCalculos>(
    `/api/v1/fiscal/is/calculos${query({
      ejercicio: filtros.ejercicio,
      provisional: filtros.provisional,
      estado: filtros.estado,
      limit: filtros.limit,
      offset: filtros.offset,
      page: filtros.page,
      page_size: filtros.page_size,
    })}`
  );
}

export function obtenerCalculo(id: string): Promise<DetalleCalculo> {
  return get<DetalleCalculo>(`/api/v1/fiscal/is/calculos/${id}`);
}

export function crearCalculo(body: {
  ejercicio: number;
  provisional: boolean;
}): Promise<DetalleCalculo> {
  return post<DetalleCalculo>("/api/v1/fiscal/is/calculos", body);
}

export function recalcularCalculo(
  id: string,
  body: { ajustes: AjusteInput[]; deducciones: AjusteInput[] }
): Promise<DetalleCalculo> {
  return post<DetalleCalculo>(`/api/v1/fiscal/is/calculos/${id}/recalcular`, body);
}

export function agregarAjuste(
  id: string,
  body: AjusteInput
): Promise<AjusteExtracontable> {
  return post<AjusteExtracontable>(`/api/v1/fiscal/is/calculos/${id}/ajustes`, body);
}

export function eliminarAjuste(id: string, ajusteId: string): Promise<unknown> {
  return remove<unknown>(`/api/v1/fiscal/is/calculos/${id}/ajustes/${ajusteId}`);
}

export function contabilizarCalculo(
  id: string,
  body: { fecha_asiento: string }
): Promise<{ asiento_id: string; estado: EstadoCalculo }> {
  return post<{ asiento_id: string; estado: EstadoCalculo }>(
    `/api/v1/fiscal/is/calculos/${id}/contabilizar`,
    body
  );
}

export function listarModelos200(filtros: FiltrosModelos200 = {}): Promise<ListaModelos200> {
  return get<ListaModelos200>(
    `/api/v1/fiscal/is/modelo-200${query({
      ejercicio: filtros.ejercicio,
      limit: filtros.limit,
      offset: filtros.offset,
    })}`
  );
}

export function generarModelo200(body: { calculo_is_id: string }): Promise<Modelo200> {
  return post<Modelo200>("/api/v1/fiscal/is/modelo-200", body);
}

export async function descargarModelo200(id: string, nombre?: string): Promise<void> {
  const blob = await requestBlob(`/api/v1/fiscal/is/modelo-200/${id}`);
  const url = URL.createObjectURL(blob);
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombre ?? `modelo-200-${id}.csv`;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  URL.revokeObjectURL(url);
}

export function obtenerConfiguracionFiscal(): Promise<ConfiguracionFiscal> {
  return get<ConfiguracionFiscal>("/api/v1/fiscal/configuracion");
}

export function actualizarConfiguracionFiscal(
  body: {
    tipo_is?: string;
    fecha_vigencia_desde?: string;
    fecha_vigencia_hasta?: string | null;
  }
): Promise<ConfiguracionFiscal> {
  return patch<ConfiguracionFiscal>("/api/v1/fiscal/configuracion", body);
}

export const listarCalculosIS = listarCalculos;
export const obtenerCalculoIS = obtenerCalculo;
export const crearCalculoIS = crearCalculo;
export const recalcularCalculoIS = recalcularCalculo;
export const agregarAjusteIS = agregarAjuste;
export const eliminarAjusteIS = eliminarAjuste;
export const contabilizarCalculoIS = contabilizarCalculo;
export const listarModelos = listarModelos200;
export const generarModelo = generarModelo200;
export const descargarModelo = descargarModelo200;

export function formatearImporte(importe: string): string {
  const limpio = importe.trim();
  const negativo = limpio.startsWith("-");
  const valor = negativo ? limpio.slice(1) : limpio;
  const partes = valor.split(".");
  const entero = partes[0] ?? "";
  const decimales = partes[1] ?? "";
  const enteroFormato = entero.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const texto = `${enteroFormato}${decimales ? `,${decimales}` : ""} €`;
  return negativo ? `-${texto}` : texto;
}

export type EstadoLiquidacion = "pendiente" | "liquidado";
export type TipoRetencion =
  | "IRPF_PROFESIONALES"
  | "IRPF_ARRENDAMIENTOS"
  | "IRPF_OBRAS"
  | "IRPF_OTROS";

export interface FacturaRetencion {
  factura_id: string;
  numero: string;
  fecha: string;
  importe_base: string;
  retencion: string;
}

export interface RetencionPeriodo {
  id: string;
  tercero_id: string;
  nif: string | null;
  nombre: string;
  tipo_retencion: TipoRetencion;
  base_imponible: string;
  tipo_porcentaje: string;
  retencion_practicada: string;
  facturas: FacturaRetencion[];
  notas?: string | null;
}

export interface LiquidacionResumen {
  id: string;
  ejercicio: number;
  trimestre: number;
  periodo?: string;
  total_base_retenciones?: string;
  total_retenciones: string;
  n_perceptores?: number;
  estado: EstadoLiquidacion;
  fecha_liquidacion: string | null;
  asiento_id?: string | null;
  modelo_111_id?: string | null;
  modelo_115_id?: string | null;
  notas?: string | null;
}

export interface ResultadoCrearLiquidacion {
  id: string;
  periodo: string;
  total_base_retenciones: string;
  total_retenciones: string;
  n_perceptores: number;
  estado: EstadoLiquidacion;
}

export interface DetalleLiquidacion extends LiquidacionResumen {
  retenciones: RetencionPeriodo[];
}

export interface ListaLiquidaciones {
  items: LiquidacionResumen[];
  total: number;
}

export interface FiltrosLiquidaciones {
  ejercicio?: number;
  trimestre?: number;
  estado?: EstadoLiquidacion;
  limit?: number;
  offset?: number;
}

export interface Modelo111 {
  id: string;
  liquidacion_id?: string;
  ejercicio?: number;
  trimestre?: number;
  fecha_generacion: string;
  hash_contenido: string;
  nombre_fichero?: string | null;
  content_type?: string | null;
}

export interface Modelo115 {
  id: string;
  liquidacion_id?: string;
  ejercicio?: number;
  trimestre?: number;
  fecha_generacion?: string;
  hash_contenido: string;
  nombre_fichero?: string | null;
  content_type?: string | null;
}

export interface Modelo190 {
  id: string;
  ejercicio: number;
  fecha_generacion: string;
  hash_contenido: string;
  n_perceptores: number;
  nombre_fichero?: string | null;
  content_type?: string | null;
}

export interface ListaModelos190 {
  items: Modelo190[];
  total: number;
}

export interface PerceptorSinNif {
  tercero_id: string;
  nombre: string;
}

export interface ValidacionNif190 {
  valido: boolean;
  perceptores_sin_nif?: PerceptorSinNif[];
}

export interface FiltrosModelos190 {
  ejercicio?: number;
  limit?: number;
  offset?: number;
}

async function descargarContenido(ruta: string, nombre: string): Promise<void> {
  const blob = await requestBlob(ruta);
  const url = URL.createObjectURL(blob);
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombre;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  URL.revokeObjectURL(url);
}

export function crearLiquidacion(body: {
  ejercicio: number;
  trimestre: number;
}): Promise<ResultadoCrearLiquidacion> {
  return post<ResultadoCrearLiquidacion>("/api/v1/fiscal/retenciones/liquidaciones", body);
}

export function listarLiquidaciones(
  filtros: FiltrosLiquidaciones = {}
): Promise<ListaLiquidaciones> {
  return get<ListaLiquidaciones>(
    `/api/v1/fiscal/retenciones/liquidaciones${query({
      ejercicio: filtros.ejercicio,
      trimestre: filtros.trimestre,
      estado: filtros.estado,
      limit: filtros.limit,
      offset: filtros.offset,
    })}`
  );
}

export function obtenerLiquidacion(id: string): Promise<DetalleLiquidacion> {
  return get<DetalleLiquidacion>(`/api/v1/fiscal/retenciones/liquidaciones/${id}`);
}

export function listarRetenciones(id: string): Promise<RetencionPeriodo[]> {
  return get<RetencionPeriodo[]>(`/api/v1/fiscal/retenciones/liquidaciones/${id}/retenciones`);
}

export function contabilizarLiquidacion(
  id: string,
  body: { fecha_asiento: string; cuenta_banco: string }
): Promise<{ asiento_id: string; estado: EstadoLiquidacion }> {
  return post<{ asiento_id: string; estado: EstadoLiquidacion }>(
    `/api/v1/fiscal/retenciones/liquidaciones/${id}/contabilizar`,
    body
  );
}

export function generarModelo111(body: { liquidacion_id: string }): Promise<Modelo111> {
  return post<Modelo111>("/api/v1/fiscal/retenciones/modelos-111", body);
}

export function descargarModelo111(id: string, nombre?: string): Promise<void> {
  return descargarContenido(
    `/api/v1/fiscal/retenciones/modelos-111/${id}`,
    nombre ?? `modelo-111-${id}.csv`
  );
}

export function generarModelo115(body: { liquidacion_id: string }): Promise<Modelo115> {
  return post<Modelo115>("/api/v1/fiscal/retenciones/modelos-115", body);
}

export function descargarModelo115(id: string, nombre?: string): Promise<void> {
  return descargarContenido(
    `/api/v1/fiscal/retenciones/modelos-115/${id}`,
    nombre ?? `modelo-115-${id}.csv`
  );
}

export function validarModelo190(ejercicio: number): Promise<ValidacionNif190> {
  return get<ValidacionNif190>(
    `/api/v1/fiscal/retenciones/modelo-190/validar${query({ ejercicio })}`
  );
}

export function generarModelo190(body: { ejercicio: number }): Promise<Modelo190> {
  return post<Modelo190>("/api/v1/fiscal/retenciones/modelo-190", body);
}

export function listarModelos190(filtros: FiltrosModelos190 = {}): Promise<ListaModelos190> {
  return get<ListaModelos190>(
    `/api/v1/fiscal/retenciones/modelo-190${query({
      ejercicio: filtros.ejercicio,
      limit: filtros.limit,
      offset: filtros.offset,
    })}`
  );
}

export function descargarModelo190(id: string, nombre?: string): Promise<void> {
  return descargarContenido(
    `/api/v1/fiscal/retenciones/modelo-190/${id}`,
    nombre ?? `modelo-190-${id}.csv`
  );
}
