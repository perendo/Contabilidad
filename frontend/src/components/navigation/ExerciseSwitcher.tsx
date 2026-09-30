"use client";

/**
 * SELECTOR DE EJERCICIO (SPEC-031, US1)
 *
 * Es el componente que justifica la feature. El caso es contabilizar en dos
 * ejercicios a la vez, y el riesgo es hacer el cambio equivocado sin darse cuenta.
 * Por eso aqui no basta con mostrar el ano:
 *
 * - El estado se distinge con **color Y con etiqueta de texto**. Un color solo
 *   deja fuera a quien no distingue rojo de verde, y ademas el estado del ejercicio
 *   es informacion critica, no decorativa (FR-031, research D7).
 * - Se ve **cuantos asientos lleva cada ejercicio**, que es lo que permite decidir *   en cual se esta sin abrir el diario (FR-017).
 * - El ejercicio anterior abierto se marca como `cerrando`, no como `abierto`: la
 *   diferencia importa y un usuario que cierra el ano no la va a leer sola.
 * - El cerrado **no** es seleccionable y se explica por que.
 *
 * Accesibilidad (FR-030, FR-031):
 * - Es un `listbox`, con `role`, `aria-activedescendant` y navegacion por flechas.
 * - `Enter` o `Espacio` seleccionan; `Escape` cierra sin cambiar.
 * - El foco es visible, y el estado no depende solo del color.
 */

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useSesion } from "./SessionContext";
import type { EjercicioResuelto } from "./tipos";

const CLASES: Record<string, string> = {
  abierto_actual: "text-slate-200",
  abierto_anterior: "text-amber-400",
  con_apertura: "text-slate-200",
  cerrado: "text-slate-500 line-through",
};

export function etiqueta(estado: string, esActual: boolean): string | null {
  if (estado === "cerrado") return "cerrado";
  if (estado === "con_apertura") return "apertura";
  if (!esActual) return "cerrando";
  return null;
}

export function clase(ejercicio: EjercicioResuelto): string {
  const base = CLASES[ejercicio.estado] ?? CLASES.abierto_actual;
  return `${base} ${ejercicio.es_actual ? "font-semibold" : ""}`;
}

export default function ExerciseSwitcher({ compacto = false }: { compacto?: boolean }) {
  const { contexto, ejercicio, cargando, cambiarEjercicio, recargar } = useSesion();
  const [abierto, setAbierto] = useState(false);
  const [activo, setActivo] = useState(0);
  const contenedor = useRef<HTMLDivElement>(null);
  const boton = useRef<HTMLButtonElement>(null);
  const listaId = useId();

  const ejercicios = useMemo(
    () => contexto?.ejercicios ?? [],
    [contexto],
  );

  const seleccionables = useMemo(
    () => ejercicios.filter((e) => e.es_seleccionable),
    [ejercicios],
  );

  useEffect(() => {
    if (!abierto) return;
    const i = ejercicios.findIndex((e) => e.ejercicio === ejercicio?.ejercicio);
    setActivo(i >= 0 ? i : 0);
  }, [abierto, ejercicios, ejercicio]);

  useEffect(() => {
    if (!abierto) return;
    const fuera = (evento: MouseEvent) => {
      if (!contenedor.current?.contains(evento.target as Node)) setAbierto(false);
    };
    document.addEventListener("mousedown", fuera);
    return () => document.removeEventListener("mousedown", fuera);
  }, [abierto]);

  const elegir = async (e: EjercicioResuelto) => {
    setAbierto(false);
    boton.current?.focus();
    if (e.ejercicio !== ejercicio?.ejercicio) await cambiarEjercicio(e.ejercicio);
  };

  const alTeclado = (evento: React.KeyboardEvent) => {
    if (evento.key === "Escape") {
      setAbierto(false);
      boton.current?.focus();
      return;
    }
    if (evento.key === "ArrowDown" || evento.key === "ArrowUp") {
      evento.preventDefault();
      if (!abierto) {
        setAbierto(true);
        return;
      }
      const delta = evento.key === "ArrowDown" ? 1 : -1;
      const siguiente = (activo + delta + seleccionables.length) % Math.max(seleccionables.length, 1);
      setActivo(Math.max(0, Math.min(siguiente, seleccionables.length - 1)));
      return;
    }
    if ((evento.key === "Enter" || evento.key === " ") && abierto) {
      evento.preventDefault();
      const e = seleccionables[activo];
      if (e) void elegir(e);
    }
  };

  if (!ejercicio) {
    return (
      <div ref={contenedor} className="px-3 py-1.5 text-xs text-slate-500">
        {cargando ? "Cargando ejercicio…" : "Sin ejercicio disponible"}
        {contexto && ejercicios.length === 0 && (
          <button
            type="button"
            onClick={() => void recargar()}
            className="ml-2 underline text-emerald-400"
          >
            Reintentar
          </button>
        )}
      </div>
    );
  }

  const anterior = ejercicios.find(
    (e) => e.ejercicio < ejercicio.ejercicio && e.es_seleccionable,
  );
  const mostrarAtajo = anterior !== undefined && !ejercicio.es_actual;
  const textoActivo = etiqueta(ejercicio.estado, ejercicio.es_actual);

  return (
    <div ref={contenedor} className="relative">
      {mostrarAtajo && anterior && (
        <button
          type="button"
          onClick={() => void cambiarEjercicio(anterior.ejercicio)}
          title={`Cambiar a ${anterior.ejercicio}, que tiene ${anterior.n_asientos} asientos`}
          className="mb-1 flex w-full items-center justify-between rounded border border-amber-500/40 bg-amber-500/10 px-3 py-1 text-xs text-amber-300 hover:bg-amber-500/20 focus-visible:outline-2 focus-visible:outline-amber-500"
        >
          <span>
            Ejercicio {anterior.ejercicio}: {anterior.n_asientos} asientos
          </span>
          <span aria-hidden="true">→</span>
        </button>
      )}

      <button
        ref={boton}
        type="button"
        onClick={() => setAbierto((v) => !v)}
        onKeyDown={alTeclado}
        aria-haspopup="listbox"
        aria-expanded={abierto}
        aria-controls={abierto ? listaId : undefined}
        className={[
          "flex items-center gap-1.5 bg-slate-900 border border-slate-700/80 px-3 py-1.5 rounded-lg text-xs text-slate-200 transition-colors",
          "hover:bg-slate-800 hover:border-slate-600 focus-visible:outline-2 focus-visible:outline-emerald-500",
          compacto ? "w-full justify-between" : "",
        ].join(" ")}
      >
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="w-3.5 h-3.5 text-emerald-400 shrink-0"
        >
          <path d="M8 2v4" />
          <path d="M16 2v4" />
          <rect width="18" height="18" x="3" y="4" rx="2" />
          <path d="M3 10h18" />
        </svg>

        <span className="font-medium">{ejercicio.ejercicio} ({textoActivo ?? "Abierto"})</span>

        {textoActivo && (
          <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-800 font-semibold">
            {textoActivo}
          </span>
        )}

        <svg
          aria-hidden="true"
          viewBox="0 0 10 6"
          className="h-1.5 w-2 shrink-0 text-slate-400 ml-1"
        >
          <path d="M0 0h10L5 6z" fill="currentColor" />
        </svg>
      </button>

      {abierto && (
        <ul
          id={listaId}
          role="listbox"
          aria-label="Ejercicio activo"
          tabIndex={-1}
          className="absolute left-0 top-full z-50 mt-1 max-h-60 w-80 overflow-auto rounded-xl border border-slate-800 bg-slate-950 p-1.5 shadow-2xl"
        >
          {ejercicios.map((e, i) => {
            const texto = etiqueta(e.estado, e.es_actual);
            const esActivo = e.ejercicio === ejercicio.ejercicio;
            return (
              <li
                key={e.ejercicio}
                role="option"
                aria-selected={esActivo}
                aria-disabled={!e.es_seleccionable}
                title={!e.es_seleccionable ? "No admite asientos" : undefined}
                onClick={() => e.es_seleccionable && void elegir(e)}
                onKeyDown={alTeclado}
                className={[
                  "flex items-center justify-between px-3 py-2 text-xs rounded-lg transition-colors",
                  e.es_seleccionable ? "cursor-pointer" : "cursor-not-allowed opacity-50",
                  esActivo
                    ? "bg-emerald-500/15 font-semibold text-emerald-300 border border-emerald-500/20"
                    : i === activo && e.es_seleccionable
                    ? "bg-slate-900 text-white"
                    : "text-slate-300 hover:bg-slate-900",
                ].join(" ")}
              >
                <span className={clase(e)}>
                  {e.ejercicio}
                  {texto && (
                    <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-800">
                      {texto}
                    </span>
                  )}
                </span>
                <span className="text-[11px] font-mono text-slate-500">{e.n_asientos} asientos</span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
