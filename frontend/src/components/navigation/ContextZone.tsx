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

  // La lista de empresas se pide aqui y no se recibe por props porque quien la consume
  // es la zona de contexto, y quien la tiene que montar es `layout.tsx`, que no tiene
  // sesion: si la lista dependiera del padre, `layout` tendria que hacer la peticion o
  // ningun componente se la pasa. Con el fetch local, la zona funciona montada sola.
  //
  // Un fallo aqui NO es un fallo de contexto: el usuario puede trabajar en la empresa
  // activa aunque no pueda cambiar. Se deja la lista vacia y el selector se limita a
  // mostrar la actual, en vez de tapar la pantalla con un error.
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
        className="border-b border-slate-200 bg-white px-4 py-2 text-sm text-slate-500"
      >
        Cargando contexto…
      </div>
    );
  }

  // El backend no pudo determinar contexto. Se dice, y se ofrece reintentar: es el
  // caso borde que anade el spec, y esconderlo dejaria al usuario mirando una
  // pantalla vacia sin saber que pasa.
  if (!contexto) {
    return (
      <div
        role="alert"
        className="border-b border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800"
      >
        {error ?? "No se pudo determinar la empresa ni el ejercicio."}
        <button
          type="button"
          onClick={() => void recargar()}
          className="ml-3 rounded border border-red-300 px-2 py-0.5 text-xs hover:bg-red-100 focus-visible:outline-2 focus-visible:outline-red-700"
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
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white">
        <div className="flex items-center justify-between gap-2 px-3 py-2">
          <button
            type="button"
            onClick={() => setHoja((v) => !v)}
            aria-expanded={hoja}
            className="flex min-w-0 items-center gap-2 rounded px-2 py-1 text-left text-sm hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-slate-900"
          >
            <span className="truncate font-medium">{empresa.nombre ?? "Sin empresa"}</span>
            <span aria-hidden="true" className="text-slate-300">/</span>
            <span className="shrink-0 font-medium">{ejercicio.ejercicio}</span>
            {ejercicio.estado !== "abierto" && (
              <span className="shrink-0 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800">
                {ejercicio.estado === "cerrado" ? "cerrado" : "cerrando"}
              </span>
            )}
          </button>
          <span className="shrink-0 truncate text-xs text-slate-600" title={usuario.email}>
            {usuario.nombre}
          </span>
        </div>
        {hoja && (
          <div className="border-t border-slate-200 bg-slate-50 px-2 py-2">
            <CompanySwitcher empresas={empresas} compacto />
            <ExerciseSwitcher compacto />
          </div>
        )}
      </header>
    );
  }

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200 bg-white">
      <div className="flex items-stretch justify-between gap-4 px-4">
        <div className="flex items-stretch gap-1 py-1">
          <CompanySwitcher empresas={empresas} />
          <ExerciseSwitcher />
        </div>
        <div className="flex items-center gap-2 py-1.5">
          <span
            className="rounded bg-slate-100 px-2 py-1 text-sm"
            title={`${usuario.email}${usuario.rol ? ` · ${usuario.rol}` : ""}`}
          >
            {usuario.nombre}
            {usuario.rol && (
              <span className="ml-2 text-xs text-slate-500">{usuario.rol}</span>
            )}
          </span>
        </div>
      </div>
    </header>
  );
}
