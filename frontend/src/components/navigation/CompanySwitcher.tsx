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

  // Sin empresas no hay nada que cambiar, pero el hueco se conserva para que la
  // zona de contexto no se descomponga: se ve que hay una empresa y no hay otras.
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
                      "text-xs",
          "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm",
          "hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-slate-900",
          unica ? "cursor-default" : "",
          compacto ? "justify-center" : "justify-start",
        ].join(" ")}
      >
        <span className="truncate font-medium">
          {cargando && !empresa ? "Cargando…" : (empresa?.nombre ?? "Sin empresa")}
        </span>
        {!unica && (
          <svg
            aria-hidden="true"
            viewBox="0 0 10 6"
            className="h-1.5 w-2.5 shrink-0 text-slate-400"
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
          className="absolute right-0 z-30 mt-1 w-72 rounded border border-slate-200 bg-white shadow-lg"
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
                      "text-xs",
                  "cursor-pointer px-3 py-2 text-sm hover:bg-slate-50",
                  i === indice ? "bg-slate-100" : "",
                ].join(" ")}
              >
                <span className={esActiva ? "font-semibold" : ""}>{e.razon_social}</span>
                {e.nif && (
                  <span className="ml-2 text-xs text-slate-500">{e.nif}</span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
