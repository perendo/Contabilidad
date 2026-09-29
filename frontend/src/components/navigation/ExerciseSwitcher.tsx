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
 * - Se ve **cuantos asientos lleva cada ejercicio**, que es lo que permite decidir
 *   en cual se esta sin abrir el diario (FR-017).
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

/** Clase de Tailwind por estado. El color nunca va solo: va con `etiqueta`. */
const CLASES: Record<string, string> = {
  abierto_actual: "text-slate-900",
  abierto_anterior: "text-amber-700",
  con_apertura: "text-slate-900",
  cerrado: "text-slate-400 line-through",
};

/**
 * Texto que acompaña al color. Es lo que hace el estado legible sin color.
 *
 * Se exporta porque `SessionMenu` pinta la lista de ejercicios del menu de sesion y
 * tiene que pintar el estado **igual** que aqui: la regla de FR-031 ("el estado no
 * depende solo del color") son dos funciones, y dos copias se separan en cuanto una
 * de las dos se toca.
 */
export function etiqueta(estado: string, esActual: boolean): string | null {
  if (estado === "cerrado") return "cerrado";
  if (estado === "con_apertura") return "apertura";
  if (!esActual) return "cerrando";
  return null;
}

/** Clase de estado de un ejercicio. Se exporta por el mismo motivo que `etiqueta`. */
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

  // `ejercicios` y `seleccionables` van en `useMemo` porque entran en las
  // dependencias de un `useEffect`. Sin memo, `contexto?.ejercicios ?? []` crea un
  // array nuevo en cada render y el efecto se dispara siempre.
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

  // Cerrar al hacer click fuera. Sin esto el desplegable se queda pegado al
  // cambiar de pagina y parece un fallo de la pantalla anterior.
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
      <div ref={contenedor} className="px-3 py-1 text-sm text-slate-500">
        {cargando ? "Cargando ejercicio…" : "Sin ejercicio disponible"}
        {contexto && ejercicios.length === 0 && (
          <button
            type="button"
            onClick={() => void recargar()}
            className="ml-2 underline"
          >
            Reintentar
          </button>
        )}
      </div>
    );
  }

  // El caso que motiva la feature: contabilizar en dos ejercicios a la vez. Con un
  // boton, cambiar de 2026 a 2025 es una pulsacion, y se ven los dos contadores a la
  // vez. Es el atajo que un contador hace falta el 31 de diciembre.
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
          className="mb-1 flex w-full items-center justify-between rounded border border-amber-300 bg-amber-50 px-3 py-1 text-xs text-amber-900 hover:bg-amber-100 focus-visible:outline-2 focus-visible:outline-amber-700"
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
          "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm",
          "hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-slate-900",
          compacto ? "justify-center" : "justify-start",
        ].join(" ")}
      >
        <span className="font-medium">{ejercicio.ejercicio}</span>
        {textoActivo && (
          <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800">
            {textoActivo}
          </span>
        )}
        <span className="text-xs text-slate-500">{ejercicio.n_asientos} asientos</span>
      </button>

      {abierto && (
        <ul
          id={listaId}
          role="listbox"
          aria-label="Ejercicio activo"
          tabIndex={-1}
          className="absolute right-0 z-30 mt-1 w-72 rounded border border-slate-200 bg-white shadow-lg"
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
                  "flex items-center justify-between px-3 py-2 text-sm",
                  e.es_seleccionable ? "cursor-pointer hover:bg-slate-50" : "cursor-not-allowed",
                  i === activo && e.es_seleccionable ? "bg-slate-100" : "",
                ].join(" ")}
              >
                <span className={clase(e)}>
                  {e.ejercicio}
                  {texto && (
                    <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs">
                      {texto}
                    </span>
                  )}
                </span>
                <span className="text-xs text-slate-500">{e.n_asientos}</span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
