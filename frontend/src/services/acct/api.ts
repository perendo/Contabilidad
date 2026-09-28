import { cabecerasEmpresa } from "@/components/treasury/empresa";
import { getToken } from "@/services/client";

export interface CuentaNodo {
  id: string;
  code: string;
  name: string;
  level: number;
  is_selectable: boolean;
  is_active: boolean;
  parent_id: string | null;
  children: CuentaNodo[];
}

export interface ArbolCuentasResponse {
  nodos: CuentaNodo[];
}

export interface CuentaSugerida {
  id: string;
  tenant_id: number;
  code: string;
  name: string;
  level: number;
  is_selectable: boolean;
  is_active: boolean;
}

export interface SugerenciasResponse {
  items: CuentaSugerida[];
}

export interface CrearCuentaRequest {
  code: string;
  name: string;
  parent_id?: string;
}

export interface CrearCuentaResponse {
  id: string;
  code: string;
  name: string;
  level: number;
  is_selectable: boolean;
  is_active: boolean;
}

export interface ActualizarCuentaRequest {
  name?: string;
  is_active?: boolean;
}

export interface ActualizarCuentaResponse {
  id: string;
  code: string;
  name: string;
  level: number;
  is_selectable: boolean;
  is_active: boolean;
  updated_at: string;
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

export async function obtenerArbolCuentas(): Promise<ArbolCuentasResponse> {
  const respuesta = await fetch("/api/v1/accounts/tree", {
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as ArbolCuentasResponse;
}

export async function sugerirCuentas(
  q: string,
  limit = 20
): Promise<SugerenciasResponse> {
  const params = new URLSearchParams();
  params.set("q", q);
  params.set("limit", String(limit));
  const respuesta = await fetch(`/api/v1/accounts/suggest?${params.toString()}`, {
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as SugerenciasResponse;
}

export async function crearCuenta(data: CrearCuentaRequest): Promise<CrearCuentaResponse> {
  const respuesta = await fetch("/api/v1/accounts", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
    body: JSON.stringify(data),
  });
  return (await manejar(respuesta)) as CrearCuentaResponse;
}

export async function actualizarCuenta(
  id: string,
  data: ActualizarCuentaRequest
): Promise<ActualizarCuentaResponse> {
  const respuesta = await fetch(`/api/v1/accounts/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
    body: JSON.stringify(data),
  });
  return (await manejar(respuesta)) as ActualizarCuentaResponse;
}

export async function obtenerCuenta(id: string): Promise<CuentaNodo> {
  const respuesta = await fetch(`/api/v1/accounts/${id}`, {
    headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
  });
  return (await manejar(respuesta)) as CuentaNodo;
}