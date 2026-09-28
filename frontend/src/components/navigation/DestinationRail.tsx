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
      className="hidden shrink-0 border-r border-slate-200 bg-slate-50 md:flex md:w-56 md:flex-col"
    >
      <ul className="flex flex-col gap-1 p-2">
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
                  "flex items-center gap-3 rounded px-3 py-2 text-sm",
                  "focus-visible:outline-2 focus-visible:outline-slate-900",
                  esActiva
                    ? "bg-white font-semibold text-slate-900 shadow-sm"
                    : "text-slate-700 hover:bg-white",
                ].join(" ")}
              >
                <span
                  aria-hidden="true"
                  className={[
                    "grid h-6 w-6 shrink-0 place-items-center rounded text-xs uppercase",
                    esActiva ? "bg-slate-900 text-white" : "bg-slate-200 text-slate-600",
                  ].join(" ")}
                >
                  {superficie.etiqueta.slice(0, 1)}
                </span>
                {superficie.etiqueta}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
