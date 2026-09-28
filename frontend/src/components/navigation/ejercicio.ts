/**
 * ALMACEN DEL EJERCICIO ACTIVO (SPEC-031, research D3)
 *
 * Espejo de `components/treasury/empresa.ts` a proposito: mismo patron, mismas
 * reglas. Si divergieran habria dos estilos de store en el mismo cliente.
 *
 * LA DIFERENCIA IMPORTANTE: el ejercicio NO es un valor global, esta indexado
 * por empresa. El mismo usuario puede estar en 2025 en la empresa A y en 2026 en
 * la empresa B, y un valor global haria que cambiar de empresa arrastrase el
 * ejercicio de la anterior (FR-004).
 *
 * NO es un limite de seguridad: es un valor por defecto que viaja en la cabecera
 * `X-Ejercicio-Activa`. El servidor lo valida contra la empresa de la sesion
 * (constitution III) y un `?ejercicio=` explicito en la URL le gana.
 */

import { getEmpresaActiva } from "@/components/treasury/empresa";

const PREFIJO = "ejercicio_activo";

/** Clave de almacenamiento: `empresa -> ejercicio`. */
type Mapa = Record<string, string>;

type Listener = (ejercicio: number | null) => void;

const listeners = new Set<Listener>();

function leerMapa(): Mapa {
  if (typeof window === "undefined") return {};
  try {
    const bruto = window.localStorage.getItem(PREFIJO);
    if (!bruto) return {};
    const parsed = JSON.parse(bruto) as unknown;
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return {};
    const limpio: Mapa = {};
    for (const [empresa, ejercicio] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof ejercicio === "string" && /^\d{4}$/.test(ejercicio)) limpio[empresa] = ejercicio;
    }
    return limpio;
  } catch {
    // Un localStorage corrupto no puede impedir usar la aplicacion.
    return {};
  }
}

function escribirMapa(mapa: Mapa): void {
  if (typeof window === "undefined") return;
  if (Object.keys(mapa).length === 0) {
    window.localStorage.removeItem(PREFIJO);
  } else {
    window.localStorage.setItem(PREFIJO, JSON.stringify(mapa));
  }
}

/** Ejercicio activo de la empresa activa, o `null` si no hay ninguno. */
export function getEjercicioActivo(): number | null {
  const empresa = getEmpresaActiva();
  if (!empresa) return null;
  const bruto = leerMapa()[empresa];
  if (!bruto) return null;
  const n = Number(bruto);
  return Number.isInteger(n) ? n : null;
}

export function setEjercicioActivo(ejercicio: number | null): void {
  if (typeof window === "undefined") return;
  const empresa = getEmpresaActiva();
  if (!empresa) return;
  const mapa = leerMapa();
  if (ejercicio === null || !Number.isInteger(ejercicio)) {
    delete mapa[empresa];
  } else {
    mapa[empresa] = String(ejercicio);
  }
  escribirMapa(mapa);
  listeners.forEach((listener) => listener(getEjercicioActivo()));
}

export function suscribirEjercicio(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/**
 * Cabecera `X-Ejercicio-Activa`. Se envia siempre que haya empresa y ejercicio,
 * y se omite si no los hay: es un valor por defecto, no un dato obligatorio, y el
 * servidor sabe resolver el ano en curso si no llega.
 */
export function cabecerasEjercicio(): Record<string, string> {
  const ejercicio = getEjercicioActivo();
  return ejercicio === null ? {} : { "X-Ejercicio-Activa": String(ejercicio) };
}

/** Todas las empresas con ejercicio elegido. Para diagnostico y para T009. */
export function mapaEjercicios(): Mapa {
  return leerMapa();
}
