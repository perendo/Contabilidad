"use client";

/**
 * NAVEGACION MOVIL (SPEC-031, T027)
 *
 * En compacto la barra inferior lleva **4 destinos y «Más»**, no los 6. No es
 * una decision de gusto: la navigation bar de M3 admite de 3 a 5 destinos, y la
 * propia especificacion dice que con mas de cinco "the elements may collide and
 * there likely won't be enough space for translated text" (research D1).
 *
 * En compacto tampoco se usa el rail: M3 dice "Don't use a standard navigation rail
 * for compact layouts due to space constraints. Use a navigation bar or a modal
 * navigation rail instead". Por eso esto es una barra, no un rail estrecho.
 *
 * «Más» abre el resto de superficies como hoja modal, no como menu desplegable
 * pegado al boton: en movil el menu desplegable es incomodo y se sale de la
 * pantalla con facilidad.
 *
 * La eleccion de cuales cuatro son los mas frecuentes la decide el producto y
 * queda declarada en `spec.md` como supuesto abierto; aqui se leen de
 * `DESTINOS_MOVIL` para que sea un solo sitio y se pueda cambiar sin tocar el
 * componente.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import {
  CLAVES_RAIL,
  sinRestricciones,
  superficieDeRuta,
  superficiePorClave,
} from "./surfaces";

/** Las cuatro superficies de la barra inferior. La quinta va en «Más». */
const DESTINOS_MOVIL = ["contabilidad", "facturacion", "tesoreria", "informes"] as const;

export default function MobileNav({
  permisos,
}: {
  permisos?: readonly (readonly [string, string])[];
}) {
  const pathname = usePathname() ?? "/";
  const [mas, setMas] = useState(false);
  const activa = superficieDeRuta(pathname)?.clave;

  useEffect(() => {
    if (!mas) return;
    const alEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMas(false);
    };
    document.addEventListener("keydown", alEsc);
    return () => document.removeEventListener("keydown", alEsc);
  }, [mas]);

  const concedida = (clave: string) => {
    const superficie = superficiePorClave(clave);
    if (!superficie) return false;
    return (
      sinRestricciones(permisos) ||
      permisos.some(
        ([m, o]) => m === superficie.permiso[0] && o === superficie.permiso[1],
      )
    );
  };

  const restantes = CLAVES_RAIL.filter(
    (c) => !(DESTINOS_MOVIL as readonly string[]).includes(c) && concedida(c),
  );

  const letra = (clave: string) =>
    superficiePorClave(clave)?.etiqueta.slice(0, 1).toUpperCase() ?? "?";

  return (
    <>
      {mas && (
        <div
          role="presentation"
          className="fixed inset-0 z-50 bg-slate-900/30 md:hidden"
          onClick={() => setMas(false)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Otras secciones"
            className="absolute inset-x-0 bottom-0 rounded-t-2xl bg-white p-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-slate-300" />
            <ul className="grid gap-1">
              {restantes.map((clave) => {
                const superficie = superficiePorClave(clave);
                if (!superficie) return null;
                return (
                  <li key={clave}>
                    <Link
                      href={superficie.landing}
                      onClick={() => setMas(false)}
                      className="block rounded px-3 py-2 text-sm hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-slate-900"
                    >
                      {superficie.etiqueta}
                    </Link>
                  </li>
                );
              })}
            </ul>
            <button
              type="button"
              onClick={() => setMas(false)}
              className="mt-2 w-full rounded border border-slate-200 px-3 py-2 text-sm"
            >
              Cerrar
            </button>
          </div>
        </div>
      )}

      <nav
        aria-label="Barra inferior de secciones"
        className="sticky bottom-0 z-40 flex border-t border-slate-200 bg-white md:hidden"
      >
        {DESTINOS_MOVIL.filter(concedida).map((clave) => {
          const superficie = superficiePorClave(clave);
          if (!superficie) return null;
          const esActiva = activa === clave;
          return (
            <Link
              key={clave}
              href={superficie.landing}
              aria-current={esActiva ? "page" : undefined}
              className={[
                "flex flex-1 flex-col items-center gap-0.5 py-2 text-xs",
                "focus-visible:outline-2 focus-visible:outline-slate-900",
                esActiva ? "font-semibold text-emerald-400" : "text-slate-600",
              ].join(" ")}
            >
              <span
                aria-hidden="true"
                className={[
                  "grid h-6 w-10 place-items-center rounded-full text-xs",
                  esActiva ? "bg-slate-900 text-white" : "",
                ].join(" ")}
              >
                {letra(clave)}
              </span>
              {superficie.etiqueta}
            </Link>
          );
        })}
        {restantes.length > 0 && (
          <button
            type="button"
            onClick={() => setMas(true)}
            aria-expanded={mas}
            className="flex flex-1 flex-col items-center gap-0.5 py-2 text-xs text-slate-600 focus-visible:outline-2 focus-visible:outline-slate-900"
          >
            <span
              aria-hidden="true"
              className="grid h-6 w-10 place-items-center rounded-full text-sm"
            >
              …
            </span>
            Más
          </button>
        )}
      </nav>
    </>
  );
}
