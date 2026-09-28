import { ApiError } from "@/components/treasury/api";
import { cabecerasEmpresa } from "@/components/treasury/empresa";
import { getToken } from "@/services/client";

export interface MasaBalance {
  codigo: string;
  nombre: string;
  importe: string;
  partidas: { nombre: string; importe: string; cuentas: string[] }[];
}

export interface BalanceReport {
  ejercicio: number;
  modo: string;
  cuadre: boolean;
  total_activo: string;
  total_pasivo: string;
  total_patrimonio: string;
  resultado_ejercicio: string;
  hay_cuentas_sin_agrupar: boolean;
  activo: MasaBalance[];
  pasivo: MasaBalance[];
  patrimonio: MasaBalance[];
  comparativo_anterior: Record<string, string> | null;
}

export interface PartidaPyg {
  grupo: string;
  nombre: string;
  importe: string;
}

export interface PygReport {
  ejercicio: number;
  modo: string;
  total_ingresos: string;
  total_gastos: string;
  resultado_ejercicio: string;
  resultado_cierre: string | null;
  coincide_cierre: boolean;
  descuadre_cierre: boolean;
  partidas: PartidaPyg[];
}

export interface ActividadEfe {
  cobros: string;
  pagos: string;
  neto: string;
}

export interface EfeReport {
  ejercicio: number;
  modo: string;
  saldo_inicial_tesoreria: string;
  actividades: Record<string, ActividadEfe>;
  variacion_neta: string;
  saldo_final_tesoreria: string;
  variacion_balance: string;
  cuadre: boolean;
}

export interface Formulacion {
  formulacion_id: string;
  ejercicio: number;
  numero_formulacion: number;
  fecha_formulacion: string;
  usuario: string | null;
  estado: "formulada" | "anulada";
  contenido_hash: string;
  motivo_anulacion: string | null;
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

export function obtenerBalance(
  ejercicio: number,
  opciones: { modo?: string; comparativo?: boolean } = {}
): Promise<BalanceReport> {
  const params = new URLSearchParams();
  if (opciones.modo) params.set("modo", opciones.modo);
  if (opciones.comparativo) params.set("comparativo", "true");
  return llamar<BalanceReport>(
    `/api/v1/cuentas-anuales/${ejercicio}/balance?${params.toString()}`
  );
}

export function obtenerPyg(
  ejercicio: number,
  opciones: { modo?: string } = {}
): Promise<PygReport> {
  const params = new URLSearchParams();
  if (opciones.modo) params.set("modo", opciones.modo);
  return llamar<PygReport>(`/api/v1/cuentas-anuales/${ejercicio}/pyg?${params.toString()}`);
}

export function obtenerEfe(
  ejercicio: number,
  opciones: { modo?: string } = {}
): Promise<EfeReport> {
  const params = new URLSearchParams();
  if (opciones.modo) params.set("modo", opciones.modo);
  return llamar<EfeReport>(`/api/v1/cuentas-anuales/${ejercicio}/efe?${params.toString()}`);
}

export function clasificarEfe(
  ejercicio: number,
  body: { movimiento_id: string; actividad: string; motivo?: string }
): Promise<{ movimiento_id: string; actividad: string }> {
  return llamar(`/api/v1/cuentas-anuales/${ejercicio}/efe/clasificacion`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function formular(ejercicio: number, observaciones?: string): Promise<Formulacion> {
  return llamar<Formulacion>(`/api/v1/cuentas-anuales/${ejercicio}/formular`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ observaciones }),
  });
}

export function anularFormulacion(
  ejercicio: number,
  motivo: string
): Promise<Formulacion> {
  return llamar<Formulacion>(`/api/v1/cuentas-anuales/${ejercicio}/anular-formulacion`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ motivo }),
  });
}

export function listarFormulaciones(
  ejercicio: number
): Promise<{ items: Formulacion[] }> {
  return llamar(`/api/v1/cuentas-anuales/${ejercicio}/formulaciones`);
}

export function guardarConfiguracion(body: {
  ejercicio: number;
  informe_tipo: string;
  agrupaciones: {
    agrupacion_codigo: string;
    agrupacion_nombre: string;
    cuenta_ini: string;
    cuenta_fin?: string | null;
    actividad_efe?: string | null;
  }[];
}): Promise<{ configuraciones_creadas: number }> {
  return llamar("/api/v1/cuentas-anuales/configuracion", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function formatearImporte(importe: string): string {
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "EUR",
  }).format(Number(importe));
}