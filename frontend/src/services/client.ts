import { ApiError } from "@/components/treasury/api";
import { cabecerasEmpresa, setEmpresaActiva } from "@/components/treasury/empresa";
import { cabecerasEjercicio } from "@/components/navigation/ejercicio";

export const TOKEN_KEY = "auth_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) {
    window.localStorage.setItem(TOKEN_KEY, token);
  } else {
    window.localStorage.removeItem(TOKEN_KEY);
  }
}

export interface SesionIniciada {
  token: string;
  default_company_id: number | null;
}

/**
 * Guarda la sesion en los dos almacenes que hacen falta, y explica por que son
 * dos (SPEC-031, research D2):
 *   - `localStorage`: el `fetch` del cliente necesita LEER el token para el
 *     encabezado `Authorization`. Una cookie `httpOnly` no se puede leer desde JS.
 *   - cookie `httpOnly`: el `middleware.ts` corre en el runtime Edge, que no
 *     puede leer `localStorage`, y solo ve cookies.
 * El token viaja al Route Handler porque solo una respuesta del servidor puede
 * marcar una cookie `httpOnly`.
 *
 * Si la cookie falla, la sesion sigue siendo utilizable: el backend no la
 * necesita. Se traga el error a proposito para que un fallo del proxy no deje al
 * usuario sin sesion en el cliente.
 */
export function guardarSesion(sesion: SesionIniciada): void {
  setToken(sesion.token);
  setEmpresaActiva(
    sesion.default_company_id !== null ? String(sesion.default_company_id) : null
  );
  void enviarCookieSesion(sesion.token);
}

export function limpiarSesion(): void {
  setToken(null);
  setEmpresaActiva(null);
  void eliminarCookieSesion();
}

async function enviarCookieSesion(token: string): Promise<void> {
  try {
    await fetch("/api/sesion", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
  } catch {
    // La cookie es para la redireccion optimista del middleware. El token que
    // vale es el del encabezado Authorization.
  }
}

async function eliminarCookieSesion(): Promise<void> {
  try {
    await fetch("/api/sesion", { method: "DELETE" });
  } catch {
    // Idem: sin cookie, el middleware deja de redirigir, pero el backend sigue
    // rechazando con 401.
  }
}

/** Cabeceras de contexto que viajan en todas las peticiones. */
function cabecerasContexto(): Record<string, string> {
  return { ...cabecerasEmpresa(), ...cabecerasEjercicio() };
}

async function manejar(respuesta: Response): Promise<unknown> {
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
  return cuerpo;
}

export async function request<T>(
  ruta: string,
  opciones: RequestInit = {}
): Promise<T> {
  const cabeceras: Record<string, string> = {
    ...((opciones.headers as Record<string, string> | undefined) ?? {}),
  };
  const token = getToken();
  if (token) cabeceras["Authorization"] = `Bearer ${token}`;
  Object.assign(cabeceras, cabecerasContexto());
  const respuesta = await fetch(ruta, { ...opciones, headers: cabeceras });
  return (await manejar(respuesta)) as T;
}

export function get<T>(ruta: string): Promise<T> {
  return request<T>(ruta);
}

export function post<T>(ruta: string, cuerpo?: unknown): Promise<T> {
  return request<T>(ruta, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
  });
}

export function patch<T>(ruta: string, cuerpo?: unknown): Promise<T> {
  return request<T>(ruta, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
  });
}

export function put<T>(ruta: string, cuerpo?: unknown): Promise<T> {
  return request<T>(ruta, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
  });
}

export function remove<T>(ruta: string): Promise<T> {
  return request<T>(ruta, { method: "DELETE" });
}

export async function requestBlob(
  ruta: string,
  opciones: RequestInit = {}
): Promise<Blob> {
  const cabeceras: Record<string, string> = {
    ...((opciones.headers as Record<string, string> | undefined) ?? {}),
  };
  const token = getToken();
  if (token) cabeceras["Authorization"] = `Bearer ${token}`;
  Object.assign(cabeceras, cabecerasContexto());
  const respuesta = await fetch(ruta, { ...opciones, headers: cabeceras });
  if (!respuesta.ok) {
    const cuerpo = (await respuesta.json().catch(() => ({}))) as {
      detail?: string | { detail?: string; code?: string };
    };
    const detalle = cuerpo.detail;
    const mensaje =
      typeof detalle === "string"
        ? detalle
        : detalle?.detail ?? `${respuesta.status} ${respuesta.statusText}`;
    const code = typeof detalle === "object" ? detalle.code : undefined;
    throw new ApiError(respuesta.status, mensaje, code);
  }
  return respuesta.blob();
}
