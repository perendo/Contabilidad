import { ApiError } from "@/components/treasury/api";
import { cabecerasEmpresa } from "@/components/treasury/empresa";
import { getToken } from "@/services/client";

export interface CatalogoModulo {
  modulo: string;
  operaciones: string[];
}

export interface Catalogo {
  modulos: CatalogoModulo[];
  total: number;
}

export interface MatrizItem {
  matriz_id: string;
  rol_id: string;
  rol: string;
  modulo: string;
  operacion: string;
  permiso_id: string;
}

export interface Matriz {
  items: MatrizItem[];
  roles: string[];
}

export interface EventoAuditoria {
  evento_id: string;
  usuario_id: number;
  rol_id: string | null;
  modulo: string;
  operacion: string;
  resultado: string;
  motivo: string;
  timestamp_utc: string;
  ip: string | null;
}

export interface MisPermisos {
  rol_id: string | null;
  rol: string | null;
  permisos: { modulo: string; operacion: string }[];
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
  if (respuesta.status === 204) return undefined as T;
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

function qs(params: Record<string, string | number | undefined>): string {
  const buscador = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== "") buscador.set(k, String(v));
  });
  return buscador.toString();
}

export function obtenerCatalogo(): Promise<Catalogo> {
  return llamar<Catalogo>("/api/v1/permisos/catalogo");
}

export function obtenerMatriz(): Promise<Matriz> {
  return llamar<Matriz>("/api/v1/permisos/matriz");
}

export function conceder(rolId: string, modulo: string, operacion: string): Promise<{ matriz_id: string }> {
  return llamar<{ matriz_id: string }>("/api/v1/permisos/matriz", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rol_id: rolId, modulo, operacion }),
  });
}

export function revocar(matrizId: string): Promise<void> {
  return llamar<void>(`/api/v1/permisos/matriz/${matrizId}`, { method: "DELETE" });
}

export function resetMatriz(): Promise<{ concesiones: number }> {
  return llamar<{ concesiones: number }>("/api/v1/permisos/matriz/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm: true }),
  });
}

export function obtenerAuditoria(filtros: {
  resultado?: string;
  modulo?: string;
  operacion?: string;
  usuario_id?: number;
  page?: number;
  page_size?: number;
}): Promise<{ items: EventoAuditoria[]; total: number }> {
  return llamar(`/api/v1/permisos/auditoria?${qs(filtros)}`);
}

export function obtenerMisPermisos(): Promise<MisPermisos> {
  return llamar<MisPermisos>("/api/v1/permisos/mis-permisos");
}

export function puedeConfigurar(mis: MisPermisos | null): boolean {
  return (
    mis?.permisos.some((p) => p.modulo === "rbac" && p.operacion === "configurar") ??
    false
  );
}

export { ApiError };
