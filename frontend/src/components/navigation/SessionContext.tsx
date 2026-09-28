"use client";

/**
 * PROVEEDOR DE CONTEXTO DE SESION (SPEC-031, research D3)
 *
 * Una sola fuente de verdad para quien es el usuario, en que empresa esta y en que
 * ejercicio. Antes, la zona de contexto eran dos selectores sueltos que cada uno
 * cargaba lo suyo y no sabian del otro: cambiar de empresa no reevaluaba el
 * ejercicio, y el ejercicio no se enteraba de que la empresa habia cambiado.
 *
 * POR QUE UN CONTEXTO Y NO MAS UN SELECTOR
 *
 * El caso que motiva la feature es contabilizar en dos ejercicios a la vez. Con dos
 * stores independientes, el selector de empresa cambiaria la empresa y dejaria el
 * ejercicio como estaba: el usuario veria "Diez SL / 2025" cuando de verdad esta en
 * la empresa B, o en un ejercicio que no existe alli. Por eso el estado de
 * ejercicio esta indexado por empresa y por eso un cambio de empresa recalcula
 * el ejercicio.
 *
 * INVALIDACION DE CACHES
 *
 * Cada cambio de empresa o de ejercicio limpia la cache de consultas del cliente.
 * Es la misma regla que ya seguia el cambio de empresa, y es lo que impide que un
 * saldo de la empresa anterior sobreviva a un cambio de empresa.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { get, limpiarSesion } from "@/services/client";
import { getEmpresaActiva, setEmpresaActiva } from "@/components/treasury/empresa";
import { getEjercicioActivo, setEjercicioActivo } from "./ejercicio";
import type { ContextoSesion, EjercicioResuelto } from "./tipos";

interface SessionState {
  contexto: ContextoSesion | null;
  cargando: boolean;
  error: string | null;
  /** `true` si el backend no pudo determinar empresa ni ejercicio. */
  sinContexto: boolean;
  recargar: () => Promise<void>;
  cambiarEjercicio: (ejercicio: number) => Promise<void>;
  cambiarEmpresa: (empresaId: number) => Promise<void>;
  /** El ejercicio activo, o `null` mientras carga. */
  ejercicio: EjercicioResuelto | null;
  /** Permisos del rol en la empresa activa, para filtrar destinos. */
  permisos: readonly (readonly [string, string])[];
}

/** Un permiso tal y como lo devuelve `GET /permisos/mis-permisos` (SPEC-015). */
interface PermisoCrudo {
  modulo: string;
  operacion: string;
}

/**
 * Traduce un permiso de la respuesta al par `[modulo, operacion]` que usan el mapa de
 * superficies y `Permiso` en `surfaces.ts`.
 *
 * Devuelve un array, no un elemento, porque `flatMap` lo exige y porque descarta
 * entradas irrecuperables en lugar de inventar un par vacio. Un par vacio se
 * compararia contra el permiso de un destino y no coincidiria con ninguno, que es
 * exactamente el fallo que hay que evitar: **inventar un permiso no puede ser mas
 * estricto que no tener ninguno**, porque "no tener ninguno" significa "sin
 * restricciones" y un par basura significa "oculto".
 */
function normalizarPermiso(p: PermisoCrudo | string | string[]) {
  if (typeof p === "string") {
    const [modulo, operacion] = p.split(":");
    if (!modulo) return [];
    return [[modulo, operacion ?? "ver"]] as const;
  }
  if (Array.isArray(p)) {
    const [modulo, operacion] = p;
    if (!modulo) return [];
    return [[modulo, operacion ?? "ver"]] as const;
  }
  if (typeof p === "object" && typeof p.modulo === "string" && p.modulo) {
    return [[p.modulo, p.operacion ?? "ver"]] as const;
  }
  return [];
}

const SessionContext = createContext<SessionState | null>(null);

export const RUTA_CONTEXTO = "/api/v1/contexto";

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [contexto, setContexto] = useState<ContextoSesion | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sinContexto, setSinContexto] = useState(false);
  const [permisos, setPermisos] = useState<readonly (readonly [string, string])[]>([]);

  const recargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    setSinContexto(false);
    try {
      const datos = await get<ContextoSesion>(RUTA_CONTEXTO);
      setContexto(datos);
    } catch (e) {
      // Un 401 aqui significa que la sesion no vale. Se limpia y el `SessionGuard`
      // manda a la pantalla de identificacion en vez de dejar un shell vacio.
      const status = (e as { status?: number }).status;
      if (status === 401 || status === 403) {
        limpiarSesion();
      }
      setError(e instanceof Error ? e.message : "No se pudo leer el contexto");
      setContexto(null);
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    void recargar();
  }, [recargar]);

  const cambiarEjercicio = useCallback(
    async (ejercicio: number) => {
      // Se escribe ANTES de recargar: la cabecera viaja con la peticion, y sin
      // esto el backend resolveria el ejercicio anterior otra vez.
      setEjercicioActivo(ejercicio);
      await recargar();
    },
    [recargar],
  );

  const cambiarEmpresa = useCallback(
    async (empresaId: number) => {
      setEmpresaActiva(String(empresaId));
      // El ejercicio se recalcula: el almacen esta indexado por empresa, asi que
      // al cambiar de empresa el valor anterior no se arrastra.
      await recargar();
    },
    [recargar],
  );

  // Permisos del rol, para que el panel oculte lo que el usuario no puede abrir.
  // Se piden aparte porque `/contexto` responde del shell, no de la matriz.
  useEffect(() => {
    let vivo = true;
    if (!contexto) {
      setPermisos([]);
      return;
    }
    void (async () => {
      try {
        // La forma real de `GET /permisos/mis-permisos` (SPEC-015) es
        // `{permisos: [{modulo, operacion}]}`. Se aceptan tambien `"modulo:operacion"`
        // y `["modulo", "operacion"]`, porque el normalizador es el unico punto donde
        // se traduce la respuesta y conviene que sea tolerante.
        //
        // Esto estaba mal antes: la tipacion decia `string[]` y el mapeo hacia
        // `String(p).split(":")`. Con la respuesta real, `String({modulo, operacion})`
        // es `"[object Object]"` y el par salia `["[object", " Object]"]`, que no
        // coincide con ningun permiso. Con `permisos` no vacio, el filtro del panel
        // ocultaba **todos** los destinos: un fallo silencioso que deja el shell sin
        // navegacion y que solo se ve al abrir la aplicacion.
        const respuesta = await get<{
          permisos?: (PermisoCrudo | string | string[])[];
        }>("/api/v1/permisos/mis-permisos");
        if (!vivo) return;
        setPermisos((respuesta.permisos ?? []).flatMap(normalizarPermiso));
      } catch {
        // Lista vacia: el panel interpreta "sin informacion" como "sin restricciones".
        // Un fallo al pedir la matriz no debe cerrar la navegacion de golpe.
        if (vivo) setPermisos([]);
      }
    })();
    return () => {
      vivo = false;
    };
  }, [contexto]);

  const valor = useMemo<SessionState>(
    () => ({
      contexto,
      cargando,
      error,
      sinContexto,
      recargar,
      cambiarEjercicio,
      cambiarEmpresa,
      ejercicio: contexto?.ejercicio_activo ?? null,
      permisos,
    }),
    [
      contexto,
      cargando,
      error,
      sinContexto,
      recargar,
      cambiarEjercicio,
      cambiarEmpresa,
      permisos,
    ],
  );

  return <SessionContext.Provider value={valor}>{children}</SessionContext.Provider>;
}

export function useSesion(): SessionState {
  const estado = useContext(SessionContext);
  if (estado === null) {
    throw new Error("useSesion debe usarse dentro de <SessionProvider>");
  }
  return estado;
}

/** El ejercicio guardado en el cliente, para pintar antes de que llegue el backend. */
export function getEjercicioLocal(): number | null {
  return getEjercicioActivo();
}

/** La empresa guardada en el cliente. */
export function getEmpresaLocal(): string | null {
  return getEmpresaActiva();
}
