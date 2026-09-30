"use client";

/**
 * RAIL DE DESTINOS (SPEC-031, T024)
 *
 * Seis destinos, orden fijo, siempre visible con iconos y etiquetas exactas a la muestra:
 * - Contabilidad (BookOpen)
 * - Facturación (FileSpreadsheet)
 * - Tesorería (Landmark + badge 032)
 * - Informes (BarChart3)
 * - Fiscal (Receipt)
 * - Maestros (Settings2)
 * - Tarjeta WORM al pie
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  CLAVES_RAIL,
  sinRestricciones,
  superficieDeRuta,
  superficiePorClave,
} from "./surfaces";

function IconoSuperficie({ clave, className }: { clave: string; className?: string }) {
  switch (clave) {
    case "contabilidad":
      return (
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
          <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z" />
          <path d="M6 6h10" />
          <path d="M6 10h10" />
        </svg>
      );
    case "facturacion":
      return (
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
          <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
          <path d="M14 2v4a2 2 0 0 0 2 2h4" />
          <path d="M8 13h2" />
          <path d="M14 13h2" />
          <path d="M8 17h2" />
          <path d="M14 17h2" />
        </svg>
      );
    case "tesoreria":
      return (
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
          <line x1="3" x2="21" y1="22" y2="22" />
          <line x1="6" x2="6" y1="18" y2="11" />
          <line x1="10" x2="10" y1="18" y2="11" />
          <line x1="14" x2="14" y1="18" y2="11" />
          <line x1="18" x2="18" y1="18" y2="11" />
          <polygon points="12 2 20 7 4 7" />
        </svg>
      );
    case "informes":
      return (
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
          <path d="M3 3v18h18" />
          <path d="M18 17V9" />
          <path d="M13 17V5" />
          <path d="M8 17v-3" />
        </svg>
      );
    case "fiscal":
      return (
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
          <path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z" />
          <path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8" />
          <path d="M12 17.5v-11" />
        </svg>
      );
    case "maestros":
    default:
      return (
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
          <path d="M20 7h-9" />
          <path d="M14 17H5" />
          <circle cx="17" cy="17" r="3" />
          <circle cx="7" cy="7" r="3" />
        </svg>
      );
  }
}

export default function DestinationRail({
  permisos,
}: {
  permisos?: readonly (readonly [string, string])[];
}) {
  const pathname = usePathname() ?? "/";
  const activa = superficieDeRuta(pathname)?.clave;

  return (
    <nav
      aria-label="Secciones del programa (barra lateral)"
      className="hidden shrink-0 border-r border-slate-800 bg-slate-950 p-3 md:flex md:w-56 md:flex-col gap-1 shrink-0"
    >
      <div className="px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
        Superficies M3
      </div>

      <ul className="flex flex-col gap-1">
        {CLAVES_RAIL.map((clave) => {
          const superficie = superficiePorClave(clave);
          if (!superficie) return null;

          const concedido =
            sinRestricciones(permisos) ||
            permisos.some(
              ([m, o]) => m === superficie.permiso[0] && o === superficie.permiso[1],
            );
          if (!concedido) return null;

          const esActiva = activa === clave;

          return (
            <li key={clave}>
              <Link
                href={superficie.landing}
                aria-current={esActiva ? "page" : undefined}
                className={[
                  "flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-medium transition-all text-left w-full whitespace-nowrap",
                  "focus-visible:outline-2 focus-visible:outline-emerald-500",
                  esActiva
                    ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 font-semibold shadow-sm"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-900/60",
                ].join(" ")}
              >
                <IconoSuperficie
                  clave={clave}
                  className={[
                    "w-4 h-4 shrink-0",
                    esActiva
                      ? "text-emerald-400"
                      : clave === "tesoreria"
                      ? "text-amber-400"
                      : clave === "facturacion"
                      ? "text-blue-400"
                      : clave === "informes"
                      ? "text-purple-400"
                      : clave === "fiscal"
                      ? "text-rose-400"
                      : "text-slate-400",
                  ].join(" ")}
                />

                <span className="flex-1">{superficie.etiqueta}</span>

                {clave === "tesoreria" && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-mono">
                    032
                  </span>
                )}
              </Link>
            </li>
          );
        })}
      </ul>

      {/* Tarjeta inferior WORM Inmutable idéntica al simulador */}
      <div className="mt-auto hidden md:block p-3 rounded-xl bg-slate-900/80 border border-slate-800 text-[11px] space-y-1.5 text-slate-400">
        <div className="text-white font-medium flex items-center gap-1.5">
          <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-3.5 h-3.5 text-emerald-400">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10" />
            <path d="m9 12 2 2 4-4" />
          </svg>
          WORM Activo
        </div>
        <div className="text-[10px] leading-relaxed text-slate-400">
          Triggers PL/pgSQL bloquean mutación de asientos POSTED.
        </div>
      </div>
    </nav>
  );
}
