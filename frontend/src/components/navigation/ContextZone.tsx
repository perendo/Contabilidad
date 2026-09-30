"use client";

/**
 * ZONA DE CONTEXTO (SPEC-031, FR-002)
 *
 * Identidad, empresa y ejercicio, juntos y **antes** de cualquier contenido de
 * negocio. Es el unico elemento que se ve en todas las pantallas, y por eso lleva
 * tres cosas que no son cosmeticas:
 *
 * 1. **La identidad.** Es el recordatorio permanente de con que usuario se esta
 *    contabilizando. Hoy el backend escribe `"system"` en el autor de los asientos
 *    creados por la API (ver SPEC-032), asi que la zona de contexto es la unica
 *    pista que tiene el usuario de quien esta registrando.
 * 2. **La empresa.** Viene de la sesion y se valida en el servidor.
 * 3. **El ejercicio.** Distinguido con color y con etiqueta de texto, con el
 *    contador de asientos a la vista.
 *
 * TAMANO MOVIL (FR-003, FR-011): en compacto la zona colapsa a un chip con empresa
 * y ejercicio juntos, porque en movil es donde mas se olvida en cual de los dos se
 * esta. El chip abre una hoja, no un desplegable pegado al boton.
 *
 * ACCESIBILIDAD (FR-030, FR-031): toda la zona es operable por teclado, el foco es
 * visible, y ningun estado se transmite solo por color.
 */

import { useCallback, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { get } from "@/services/client";
import { useSesion } from "./SessionContext";
import CompanySwitcher, { type EmpresaResumen } from "./CompanySwitcher";
import ExerciseSwitcher from "./ExerciseSwitcher";
import SessionMenu from "./SessionMenu";

/** Corte de M3: por debajo de 600dp la zona colapsa (research D1). */
const CORTE_COMPACTO = 640;

interface RespuestaEmpresas {
  items: EmpresaResumen[];
}

function useCompacto(): boolean {
  const [compacto, setCompacto] = useState(false);
  useEffect(() => {
    const mql = window.matchMedia(`(max-width: ${CORTE_COMPACTO}px)`);
    const sync = () => setCompacto(mql.matches);
    sync();
    mql.addEventListener("change", sync);
    return () => mql.removeEventListener("change", sync);
  }, []);
  return compacto;
}

export default function ContextZone({
  empresas: empresasInyectadas,
}: {
  /** Solo para tests. Si no se pasa, la lista se pide a la API. */
  empresas?: EmpresaResumen[];
}) {
  const pathname = usePathname();
  const { contexto, cargando, error, recargar } = useSesion();
  const compacto = useCompacto();
  const [hoja, setHoja] = useState(false);
  const [empresas, setEmpresas] = useState<EmpresaResumen[]>(
    empresasInyectadas ?? [],
  );

  const cargarEmpresas = useCallback(async () => {
    if (pathname === "/login") return;
    if (empresasInyectadas !== undefined) return;
    try {
      const r = await get<RespuestaEmpresas>("/api/v1/companies");
      setEmpresas(r.items ?? []);
    } catch {
      setEmpresas([]);
    }
  }, [empresasInyectadas]);

  useEffect(() => {
    void cargarEmpresas();
  }, [cargarEmpresas]);

  useEffect(() => {
    if (!hoja) return;
    const alEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setHoja(false);
    };
    document.addEventListener("keydown", alEsc);
    return () => document.removeEventListener("keydown", alEsc);
  }, [hoja]);

  if (pathname === "/login") return null;

  if (cargando && !contexto) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="border-b border-slate-800 bg-slate-950 px-4 py-2.5 text-xs text-slate-400"
      >
        Cargando contexto…
      </div>
    );
  }

  if (!contexto) {
    return (
      <div
        role="alert"
        className="border-b border-rose-900/40 bg-rose-950/30 px-4 py-2.5 text-xs text-rose-300"
      >
        {error ?? "No se pudo determinar la empresa ni el ejercicio."}
        <button
          type="button"
          onClick={() => void recargar()}
          className="ml-3 rounded border border-rose-700/60 bg-rose-900/40 px-2.5 py-0.5 text-xs hover:bg-rose-900/80 focus-visible:outline-2 focus-visible:outline-rose-500"
        >
          Reintentar
        </button>
      </div>
    );
  }

  const { usuario, empresa } = contexto;
  const ejercicio = contexto.ejercicio_activo;

  if (compacto) {
    return (
      <header className="sticky top-0 z-40 border-b border-slate-800 bg-slate-950/90 backdrop-blur">
        <div className="flex items-center justify-between gap-2 px-3 py-2">
          <button
            type="button"
            onClick={() => setHoja((v) => !v)}
            aria-expanded={hoja}
            className="flex min-w-0 items-center gap-2 rounded-lg px-2.5 py-1 text-left text-xs bg-slate-900 border border-slate-800 text-slate-200 hover:bg-slate-800 focus-visible:outline-2 focus-visible:outline-emerald-500"
          >
            <span className="truncate font-medium">{empresa.nombre ?? "Sin empresa"}</span>
            <span aria-hidden="true" className="text-slate-600">/</span>
            <span className="shrink-0 font-medium">{ejercicio.ejercicio}</span>
            {ejercicio.estado !== "abierto" && (
              <span className="shrink-0 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800">
                {ejercicio.estado === "cerrado" ? "cerrado" : "cerrando"}
              </span>
            )}
          </button>
          <span className="shrink-0 truncate text-xs text-slate-400" title={usuario.email}>
            {usuario.nombre}
          </span>
        </div>

        {hoja && (
          <div className="border-t border-slate-800 bg-slate-900/90 px-3 py-3 space-y-2">
            <CompanySwitcher empresas={empresas} compacto />
            <ExerciseSwitcher compacto />
            <div className="mt-2 border-t border-slate-800 pt-2">
              <SessionMenu empresas={empresas} />
            </div>
          </div>
        )}
      </header>
    );
  }

  return (
    <header className="sticky top-0 z-40 bg-slate-950/90 border-b border-slate-800 px-4 sm:px-6 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Brand / Logo badge EXACTO a la muestra */}
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 font-bold text-sm">
            PGC
          </div>
          <div>
            <div className="text-xs font-semibold text-white flex items-center gap-1.5">
              <span>Contabilidad PGC Español</span>
              <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-300 font-mono">
                v1.4.0
              </span>
            </div>
            <div className="text-[11px] text-slate-400">Sistema Contable de Producción</div>
          </div>
        </div>

        {/* Tenant & Exercise Switcher Chips con iconos a juego */}
        <div className="flex items-center flex-wrap gap-2 text-xs">
          <CompanySwitcher empresas={empresas} />
          <ExerciseSwitcher />
          <SessionMenu empresas={empresas} />
        </div>
      </div>
    </header>
  );
}
