"use client";

/**
 * RAIL DE DESTINOS (SPEC-031, T024)
 *
 * Seis destinos, orden fijo, siempre visible. Las reglas que cumple estan todas
 * comprobadas por `backend/tests/unit/test_navegacion_invariantes.py`:
 *
 * - **Orden estable** (FR-009). No se reordena por uso, ni por frecuencia, ni por
 *   favoritos. Es lo que hace la navegacion predecible; si el rail se moviera solo,
 *   el usuario tendria que buscarlo otra vez cada dia.
 * - **Un solo indicador activo** (M3: "Don't use the active indicator for more than
 *   one navigation item at a time").
 * - **Icono y etiqueta siempre** (M3: "Don't remove the labels"). Se acorta la
 *   etiqueta, no se trunca.
 * - **En el mismo sitio** en todas las pantallas (M3: "Always put the rail in the
 *   same place").
 *
 * ACCESIBILIDAD (FR-030): es un `nav` con `aria-label`, cada destino es un enlace
 * real (`Link`) para que funcione con el teclado, con teclado gestionado, y el
 * indicador activo no depende solo del color: el activo tiene ademas fondo y peso.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  CLAVES_RAIL,
  sinRestricciones,
  superficieDeRuta,
  superficiePorClave,
} from "./surfaces";

export default function DestinationRail({
  permisos,
}: {
  /** Pares `modulo:operacion` concedidos. Un destino sin permiso no se muestra. */
  permisos?: readonly (readonly [string, string])[];
}) {
  const pathname = usePathname() ?? "/";
  const activa = superficieDeRuta(pathname)?.clave;

  return (
    <nav
      aria-label="Secciones del programa (barra lateral)"
      className="hidden shrink-0 border-r border-slate-800 bg-slate-950 md:flex md:w-56 md:flex-col"
    >
      <div className="px-4 pt-4 pb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
        Superficies M3
      </div>
      <ul className="flex flex-col gap-1.5 p-3">
        {CLAVES_RAIL.map((clave) => {
          const superficie = superficiePorClave(clave);
          if (!superficie) return null;

          // El rail muestra superficies enteras, no destinos, asi que el permiso que
          // decide es el de la propia superficie. Ocultar un destino suelto dejaria
          // un rail con huecos, que es justo lo que el caso borde prohibe.
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
                  "flex items-center gap-3 rounded-xl px-3 py-2.5 text-xs font-medium transition-all",
                  "focus-visible:outline-2 focus-visible:outline-emerald-500",
                  esActiva
                    ? "border border-emerald-500/30 bg-emerald-500/15 font-semibold text-emerald-300 shadow-sm"
                    : "text-slate-400 hover:bg-slate-900/60 hover:text-slate-200",
                ].join(" ")}
              >
                <span
                  aria-hidden="true"
                  className={[
                    "grid h-6 w-6 shrink-0 place-items-center rounded-lg text-xs uppercase font-bold",
                    esActiva
                      ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                      : "bg-slate-900 text-slate-400 border border-slate-800",
                  ].join(" ")}
                >
                  {superficie.etiqueta.slice(0, 1)}
                </span>
                <span className="flex-1">{superficie.etiqueta}</span>
                {clave === "tesoreria" && (
                  <span className="rounded bg-emerald-500/20 px-1.5 py-0.5 font-mono text-[9px] text-emerald-300">
                    032
                  </span>
                )}
              </Link>
            </li>
          );
        })}
      </ul>
      <div className="mt-auto hidden p-4 md:block">
        <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-3 text-[11px] text-slate-400 space-y-1">
          <div className="font-semibold text-white flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400"></span>
            WORM Inmutable
          </div>
          <p className="text-[10px] text-slate-400 leading-relaxed">
            Triggers PL/pgSQL activos en diario y asientos.
          </p>
        </div>
      </div>
    </nav>
  );
}
