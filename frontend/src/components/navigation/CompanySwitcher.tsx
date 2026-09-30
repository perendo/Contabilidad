"use client";

/**
 * SELECTOR DE EMPRESA (SPEC-031, US1)
 *
 * Reutiliza el almacen y los tokens que ya tenia `components/rbac/CompanySwitch.tsx`,
 * que es quien sabe listar las empresas del usuario. No se reimplementa la lista:
 * se pide al mismo sitio, y por eso este componente no duplica esa logica.
 *
 * Lo que cambia respecto al selector viejo es que el cambio de empresa **recalcula
 * el ejercicio** (FR-004). Con dos almacenes independientes, cambiar de empresa
 * dejaba el ejercicio como estaba y el usuario veia una combinacion imposible.
 *
 * Accesibilidad: mismo contrato de teclado que `ExerciseSwitcher` (FR-030).
 */

import { useEffect, useRef, useState } from "react";
import { useSesion } from "./SessionContext";

export interface EmpresaResumen {
  company_id: number;
  razon_social: string;
  nif?: string | null;
  is_active?: boolean;
}

export default function CompanySwitcher({
  empresas,
  compacto = false,
}: {
  empresas: EmpresaResumen[];
  compacto?: boolean;
}) {
  const { contexto, cambiarEmpresa, cargando } = useSesion();
  const [abierto, setAbierto] = useState(false);
  const contenedor = useRef<HTMLDivElement>(null);
  const boton = useRef<HTMLButtonElement>(null);
  const [indice, setIndice] = useState(0);

  useEffect(() => {
    if (!abierto) return;
    const fuera = (evento: MouseEvent) => {
      if (!contenedor.current?.contains(evento.target as Node)) setAbierto(false);
    };
    document.addEventListener("mousedown", fuera);
    return () => document.removeEventListener("mousedown", fuera);
  }, [abierto]);

  const unica = empresas.length <= 1;

  const elegir = async (empresa: EmpresaResumen) => {
    setAbierto(false);
    boton.current?.focus();
    if (empresa.company_id !== contexto?.empresa.id) {
      await cambiarEmpresa(empresa.company_id);
    }
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
      const n = empresas.length;
      setIndice((i) => (i + delta + n) % Math.max(n, 1));
      return;
    }
    if ((evento.key === "Enter" || evento.key === " ") && abierto) {
      evento.preventDefault();
      const e = empresas[indice];
      if (e) void elegir(e);
    }
  };

  const empresa = contexto?.empresa;

  return (
    <div ref={contenedor} className="relative">
      <button
        ref={boton}
        type="button"
        onClick={() => !unica && setAbierto((v) => !v)}
        onKeyDown={alTeclado}
        disabled={unica}
        aria-haspopup={unica ? undefined : "listbox"}
        aria-expanded={abierto}
        title={unica ? "Solo tiene acceso a esta empresa" : "Cambiar de empresa"}
        className={[
          "flex items-center gap-1.5 bg-slate-900 border border-slate-700/80 px-3 py-1.5 rounded-lg text-xs text-slate-200 transition-colors",
          unica ? "cursor-default" : "hover:bg-slate-800 hover:border-slate-600 focus-visible:outline-2 focus-visible:outline-emerald-500",
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
          className="w-3.5 h-3.5 text-indigo-400 shrink-0"
        >
          <path d="M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z" />
          <path d="M6 12H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2" />
          <path d="M18 9h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2" />
          <path d="M10 6h4" />
          <path d="M10 10h4" />
          <path d="M10 14h4" />
          <path d="M10 18h4" />
        </svg>

        <span className="truncate font-medium max-w-[14rem]">
          {cargando && !empresa ? "Cargando…" : (empresa?.nombre ?? "Sin empresa")}
        </span>

        {!unica && (
          <svg
            aria-hidden="true"
            viewBox="0 0 10 6"
            className="h-1.5 w-2 shrink-0 text-slate-400 ml-1"
          >
            <path d="M0 0h10L5 6z" fill="currentColor" />
          </svg>
        )}
      </button>

      {abierto && !unica && (
        <ul
          role="listbox"
          aria-label="Empresa activa"
          tabIndex={-1}
          className="absolute left-0 top-full z-50 mt-1 max-h-60 w-72 overflow-auto rounded-xl border border-slate-800 bg-slate-950 p-1.5 shadow-2xl"
        >
          {empresas.map((e, i) => {
            const esActiva = e.company_id === empresa?.id;
            return (
              <li
                key={e.company_id}
                role="option"
                aria-selected={esActiva}
                onClick={() => void elegir(e)}
                onKeyDown={alTeclado}
                className={[
                  "cursor-pointer px-3 py-2 text-xs rounded-lg transition-colors flex items-center justify-between",
                  esActiva
                    ? "bg-emerald-500/15 font-semibold text-emerald-300 border border-emerald-500/20"
                    : i === indice
                    ? "bg-slate-900 text-white"
                    : "text-slate-300 hover:bg-slate-900",
                ].join(" ")}
              >
                <span className="truncate">{e.razon_social}</span>
                {e.nif && (
                  <span className="ml-2 text-[10px] font-mono text-slate-500 shrink-0">{e.nif}</span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
