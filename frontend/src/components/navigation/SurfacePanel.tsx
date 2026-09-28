"use client";

/**
 * PANEL DE LA SUPERFICIE (SPEC-031, T025)
 *
 * El contenido de la superficie activa. NO es un drawer: M3 Expressive deja de
 * recomendar el navigation drawer y lo sustituye por el expanded navigation rail,
 * que hace lo mismo y adapta mejor entre tamaños (research D1). Por eso el panel va
 * pegado al rail, no como menu flotante.
 *
 * Qué contiene, en este orden:
 *
 * 1. **Favoritos**, si los hay (T070: si no hay, la sección no aparece y no deja
 *    un hueco ni un mensaje de configuracion). Los favoritos van ENCIMA de todo y no
 *    tocan el rail (FR-023).
 * 2. **Resumen de la superficie**, que es lo que hace util un landing. Lo monta el
 *    propio panel (`ResumenSuperficie`) y solo en la landing de cada superficie, en
 *    lugar de pasarlo desde la página: el panel vive en el layout raíz, así que una
 *    prop obligaría a subirla por `AppShell` y `layout.tsx`, que no conocen la
 *    superficie. El panel ya la deduce de la ruta.
 * 3. **Destinos de la superficie**, agrupados. Las acciones NO salen (FR-013): son
 *    acciones de la pantalla donde se aplican.
 *
 * ACCESIBILIDAD: la navegacion es una lista de enlaces reales, y el agrupado usa
 * encabezados de nivel 2 con `aria-labelledby`, de modo que un lector de pantalla
 * anuncia el grupo antes de sus destinos.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import FavoritesBar from "./FavoritesBar";
import ResumenSuperficie from "./ResumenSuperficie";
import {
  destinosAgrupados,
  sinRestricciones,
  superficieDeRuta,
  superficiePorClave,
} from "./surfaces";

export default function SurfacePanel({
  children,
  permisos,
  acciones,
}: {
  /** El contenido de la pagina. */
  children?: ReactNode;
  permisos?: readonly (readonly [string, string])[];
  /** Acciones de la superficie, fuera de la lista de destinos. */
  acciones?: ReactNode;
}) {
  const pathname = usePathname() ?? "/";
  const clave = superficieDeRuta(pathname)?.clave;
  const superficie = clave ? superficiePorClave(clave) : undefined;
  const grupos = superficie && clave ? destinosAgrupados(clave) : [];
  const rutaActiva = pathname.replace(/\/$/, "") || "/";
  // El resumen se pinta solo en la landing. El panel ya sabe la superficie y la ruta,
  // así que no hace falta que cada página pase nada: en una pantalla de detalle el
  // contador del ejercicio sería ruido al lado de los datos que ya se están viendo.
  const esLanding = superficie !== undefined && rutaActiva === superficie.landing;

  return (
    <div className="min-w-0 flex-1">
      <div className="mx-auto flex max-w-5xl flex-col gap-6 p-4 md:p-6">
        <FavoritesBar permisos={permisos} />

        {esLanding && clave && <ResumenSuperficie superficie={clave} />}

        {acciones && <section aria-label="Acciones">{acciones}</section>}

        {superficie && grupos.length > 0 && (
          <section aria-label={`Opciones de ${superficie.etiqueta}`}>
            {grupos.map((grupo) => {
              const id = `grupo-${superficie.clave}-${grupo.grupo ?? "general"}`;
              return (
                <div key={id} className="mb-5" role="group" aria-labelledby={id}>
                  {grupo.grupo && (
                    <h2
                      id={id}
                      className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500"
                    >
                      {grupo.grupo}
                    </h2>
                  )}
                  <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    {grupo.destinos.map((destino) => {
                      const concedido =
                        sinRestricciones(permisos) ||
                        permisos.some(
                          ([m, o]) =>
                            m === destino.permiso[0] && o === destino.permiso[1],
                        );
                      // Un destino sin permiso NO se oculta en silencio: se oculta y
                      // ya. Un favorito que pierde el permiso se oculta aqui, pero
                      // se conserva en la base (FR-024), de modo que si el permiso
                      // vuelve, el favorito sigue ahi.
                      if (!concedido) return null;
                      const esActivo = rutaActiva === destino.ruta.replace(/\/$/, "");
                      return (
                        <li key={destino.clave}>
                          <Link
                            href={destino.ruta}
                            aria-current={esActivo ? "page" : undefined}
                            className={[
                              "block rounded border px-3 py-2 text-sm",
                              "focus-visible:outline-2 focus-visible:outline-slate-900",
                              esActivo
                                ? "border-slate-900 bg-white font-semibold"
                                : "border-slate-200 bg-white hover:border-slate-400",
                            ].join(" ")}
                          >
                            {destino.etiqueta}
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              );
            })}
          </section>
        )}

        {!superficie && (
          <p className="text-sm text-slate-500">
            Esta pantalla no pertenece a ninguna superficie. Si deberia, el mapa de
            superficies esta incompleto.
          </p>
        )}
        {children}
      </div>
    </div>
  );
}
