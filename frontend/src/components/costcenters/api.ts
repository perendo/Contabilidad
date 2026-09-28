import { get, getToken, post, request } from "../../services/client";
import { cabecerasEmpresa } from "../treasury/empresa";

export interface CentroCoste {
  id: string;
  codigo: string;
  nombre: string;
  tipo: string;
  parent_id: string | null;
  subvencion_id: string | null;
  estado: string;
  es_hoja: boolean;
  created_at?: string | null;
}

export interface CentroNodo extends CentroCoste {
  profundidad: number;
  n_hijos: number;
  hijos: CentroNodo[];
}

export interface PaginaCentros {
  items: CentroCoste[];
  total: number;
  page: number;
  page_size: number;
}

export interface Imputacion {
  id: string;
  asiento_id: string;
  linea_id: string;
  centro_coste_id: string;
  codigo: string | null;
  nombre: string | null;
  linea_cuenta: string | null;
}

export interface FilaInforme {
  centro_id: string;
  codigo: string;
  nombre: string;
  parent_id: string | null;
  directo_debe: string;
  directo_haber: string;
  hijos_debe: string;
  hijos_haber: string;
  subtotal_debe: string;
  subtotal_haber: string;
  subtotal: string;
}

export interface InformeCostes {
  filas: FilaInforme[];
  totales: { coste: string; ingreso: string; neto: string };
  n_filas: number;
}

export function listarCentros(params: Record<string, string | number> = {}): Promise<PaginaCentros> {
  const qs = new URLSearchParams(
    Object.entries(params).map(([k, v]) => [k, String(v)])
  );
  return get<PaginaCentros>(`/api/v1/centros?${qs}`);
}

export async function arbolCentros(): Promise<CentroNodo[]> {
  const cuerpo = await get<{ items: CentroNodo[]; total: number }>("/api/v1/centros/arbol");
  return cuerpo.items;
}

export function aplanarArbol(nodos: CentroNodo[]): CentroCoste[] {
  const salida: CentroCoste[] = [];
  const recorrer = (lista: CentroNodo[]) => {
    for (const n of lista) {
      salida.push(n);
      recorrer(n.hijos ?? []);
    }
  };
  recorrer(nodos);
  return salida;
}

export function crearCentro(body: Record<string, unknown>): Promise<CentroCoste> {
  return post<CentroCoste>("/api/v1/centros", body);
}

export function obtenerCentro(id: string): Promise<CentroCoste> {
  return get<CentroCoste>(`/api/v1/centros/${id}`);
}

export function editarCentro(
  id: string,
  body: Record<string, unknown>
): Promise<CentroCoste> {
  return request<CentroCoste>(`/api/v1/centros/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function inactivarCentro(id: string): Promise<CentroCoste> {
  return post<CentroCoste>(`/api/v1/centros/${id}/inactivar`);
}

export function reactivarCentro(id: string): Promise<CentroCoste> {
  return post<CentroCoste>(`/api/v1/centros/${id}/reactivar`);
}

export function informeCostes(
  params: Record<string, string | number>
): Promise<InformeCostes> {
  const qs = new URLSearchParams(
    Object.entries(params).map(([k, v]) => [k, String(v)])
  );
  return get<InformeCostes>(`/api/v1/informes/costes?${qs}`);
}

export async function descargarInforme(
  params: Record<string, string | number>
): Promise<void> {
  const qs = new URLSearchParams(
    Object.entries(params).map(([k, v]) => [k, String(v)])
  );
  const ruta = `/api/v1/informes/costes/exportar?${qs}`;
  const respuesta = await fetch(ruta, {
    headers: { Authorization: `Bearer ${getToken()}`, ...cabecerasEmpresa() },
  });
  if (!respuesta.ok) throw new Error("No se pudo exportar el informe");
  const blob = await respuesta.blob();
  const url = URL.createObjectURL(blob);
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = `informe_costes_${String(params.ejercicio)}.csv`;
  enlace.click();
  URL.revokeObjectURL(url);
}