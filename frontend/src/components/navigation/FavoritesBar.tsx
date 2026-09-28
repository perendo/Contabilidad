"use client";

/**
 * BARRA DE FAVORITOS (SPEC-031, US4, tareas T044, T070, T072)
 *
 * Seccion propia, encima del panel, **sin tocar el rail** (FR-023). Es una
 * adicion, no una sustitucion: si los favoritos reemplazaran al rail, la navegacion
 * dejaria de ser predecible, que es el principio que M3 protege.
 *
 * CUATRO REGLAS QUE PARECEN DETALLE Y NO LO SON
 *
 * 1. **Sin favoritos, no hay seccion.** Ni un hueco, ni un mensaje de "no tienes
 *    favoritos" (FR-027, T070). Un usuario recien llegado ve sus destinos y punto.
 * 2. **Un favorito que ya no se puede abrir no se borra: se ofrece retirar**
 *    (FR-024, T072). Si la ruta se reubico, la fila sigue en el servidor y MUST
 *    reaparecer si el destino vuelve. Ocultarla sin mas dejaria al usuario con un
 *    favorito que no puede quitar, que es la mitad del problema sin la otra mitad.
 * 3. **Pasarse de 5 no es un error** (CHK025). El servidor guarda todos y recorta la
 *    lectura a 5. Aqui solo se AVISA de que hay mas; no se pueden desplegar, porque la
 *    lectura ya viene recortada y no hay endpoint que devuelva el resto.
 * 4. **La cuenta la da el servidor.** Se comparan `total` y `visibles` de la respuesta,
 *    no se cuenta aqui: un segundo contador en el cliente es un segundo numero que se
 *    puede quedar viejo.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { get, remove } from "@/services/client";
import { destinoPorClave, sinRestricciones } from "./surfaces";

interface Favorito {
  destino: string;
  orden: number;
  /** El servidor ya lo resolvio con los permisos del usuario. */
  accesible: boolean;
  /** La clave no esta en el mapa: la ruta se movio. */
  desconocido?: boolean;
}

interface RespuestaFavoritos {
  items: Favorito[];
  total: number;
  visibles: number;
}

export default function FavoritesBar({
  permisos,
}: {
  permisos?: readonly (readonly [string, string])[];
}) {
  const [datos, setDatos] = useState<RespuestaFavoritos | null>(null);

  const cargar = useCallback(async () => {
    try {
      setDatos(await get<RespuestaFavoritos>("/api/v1/favoritos"));
    } catch {
      // Sin favoritos no hay seccion. Un fallo al leerlos no puede romper la pagina.
      setDatos(null);
    }
  }, []);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const desmarcar = useCallback(
    async (destino: string) => {
      // `DELETE /favoritos/{destino}` y no un POST a `/desmarcar`: el recurso que
      // desaparece es el favorito, y por eso se borra con DELETE. Un verbo distinto
      // obligaria al cliente a saber de antemano que existe una sublengua de acciones.
      try {
        await remove(`/api/v1/favoritos/${destino}`);
      } catch {
        // Se ignora y se recarga: la respuesta del servidor dirá la verdad. Un fallo
        // puntual no puede dejar la interfaz mostrando algo que ya no existe.
      }
      await cargar();
    },
    [cargar],
  );

  if (datos === null) return null;

  // Se separa en dos grupos porque se muestran y se comportan distinto: los utilizables
  // son enlaces, y los que no se pueden abrir son solo la via para retirarlos.
  const utilizables: Favorito[] = [];
  const retiradobles: Favorito[] = [];
  for (const favorito of datos.items) {
    const destino = destinoPorClave(favorito.destino);
    const permitido =
      sinRestricciones(permisos) ||
      (destino !== undefined &&
        permisos.some(
          ([m, o]) => m === destino.permiso[0] && o === destino.permiso[1],
        ));
    if (destino !== undefined && favorito.accesible && permitido) {
      utilizables.push(favorito);
    } else {
      retiradobles.push(favorito);
    }
  }

  // Sin favoritos utilizables no hay seccion, pero los retirables se ofrecen igual:
  // si estan, es porque el usuario los marco en algun momento y hay que darle la
  // occasion de limpiarlos (FR-024).
  if (utilizables.length === 0 && retiradobles.length === 0) return null;

  return (
    <section aria-label="Favoritos">
      {(utilizables.length > 0 || retiradobles.length > 0) && (
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Favoritos
          </h2>
          {datos.total > datos.visibles && (
            <span className="text-xs text-slate-500">
              {datos.total} guardados, {datos.visibles} visibles
            </span>
          )}
        </div>
      )}

      {utilizables.length > 0 && (
        <ul className="mb-2 flex flex-wrap gap-2">
          {utilizables.map((favorito) => {
            const destino = destinoPorClave(favorito.destino);
            if (destino === undefined) return null;
            return (
              <li key={favorito.destino} className="flex items-center">
                <Link
                  href={destino.ruta}
                  className="rounded-l border border-slate-200 bg-white px-3 py-1.5 text-sm hover:border-slate-400 focus-visible:outline-2 focus-visible:outline-slate-900"
                >
                  {destino.etiqueta}
                </Link>
                <Borrar destino={favorito.destino} etiqueta={destino.etiqueta} onBorrar={desmarcar} />
              </li>
            );
          })}
        </ul>
      )}

      {retiradobles.length > 0 && (
        <div className="mb-2">
          <p className="mb-1 text-xs text-slate-500">
            {retiradobles.length === 1
              ? "1 favorito ya no está disponible. Puedes retirarlo:"
              : `${retiradobles.length} favoritos ya no están disponibles. Puedes retirarlos:`}
          </p>
          <ul className="flex flex-wrap gap-2">
            {retiradobles.map((favorito) => {
              const destino = destinoPorClave(favorito.destino);
              return (
                <li key={favorito.destino} className="flex items-center gap-1">
                  <span className="text-sm text-slate-400 line-through">
                    {destino?.etiqueta ?? favorito.destino}
                  </span>
                  <button
                    type="button"
                    onClick={() => void desmarcar(favorito.destino)}
                    className="rounded border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:border-slate-400 focus-visible:outline-2 focus-visible:outline-slate-900"
                  >
                    Retirar
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
}

function Borrar({
  destino,
  etiqueta,
  onBorrar,
}: {
  destino: string;
  etiqueta: string;
  onBorrar: (destino: string) => Promise<void>;
}) {
  return (
    <button
      type="button"
      onClick={() => void onBorrar(destino)}
      title={`Quitar ${etiqueta} de favoritos`}
      aria-label={`Quitar ${etiqueta} de favoritos`}
      className="rounded-r border border-l-0 border-slate-200 bg-white px-2 py-1.5 text-sm text-slate-500 hover:text-red-700 focus-visible:outline-2 focus-visible:outline-slate-900"
    >
      <svg aria-hidden="true" viewBox="0 0 10 10" className="h-2.5 w-2.5">
        <path d="M0 0l10 10M10 0L0 10" stroke="currentColor" strokeWidth="1.5" />
      </svg>
    </button>
  );
}
