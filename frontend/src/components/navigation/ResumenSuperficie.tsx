"use client";

/**
 * RESUMEN DE SUPERFICIE (SPEC-031, US5, T046-T053)
 *
 * Las cifras de cómo va el área, en el ejercicio que el usuario tiene seleccionado.
 * `GET /api/v1/resumenes/{superficie}` las trae todas juntas, y eso es deliberado: el
 * panel pediría entre cinco y seis llamadas si las compusiera, cada una con su propio
 * error, y una que fallara dejaría un hueco sin poder distinguir "no hay datos" de "no
 * se pudo saber".
 *
 * POR QUÉ LO MONTA EL PANEL Y NO CADA LANDING
 * --------------------------------------------
 *
 * El `SurfacePanel` vive en el layout raíz, así que ninguna página puede pasarle props.
 * Si el resumen fuera una prop, habría que subirlo por `AppShell` y `layout.tsx`, que
 * no conocen la superficie activa, y el resultado sería el mismo prop drilling que el
 * shell evita para los permisos. Montándolo aquí se apoya en un dato que el panel ya
 * tiene: la superficie se deduce de la ruta.
 *
 * Solo se pinta en la LANDING de cada superficie. En una pantalla de detalle el resumen
 * sería ruido: el usuario ya está viendo los datos de un asiento, y un contador del
 * ejercicio al lado no le aporta nada.
 *
 * UN EJERCICIO CERRADO TAMBIÉN SE RESUME
 * -------------------------------------
 *
 * El endpoint admite un año cerrado a propósito, mientras que la cabecera que gobierna
 * la escritura lo rechaza. Consultar el resumen de un ejercicio cerrado es la pregunta
 * más natural que se le puede hacer a un cierre, y responder con los números de otro
 * ejercicio sería peor que un error.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { get } from "@/services/client";

interface Metrica {
  clave: string;
  etiqueta: string;
  valor: string | number;
  unidad?: string;
}

interface Enlace {
  clave: string;
  etiqueta: string;
  ruta: string;
}

interface Resumen {
  superficie: string;
  empresa_id: number;
  ejercicio: number | null;
  /** `sin_ejercicio` cuando la empresa aún no tiene ningún ejercicio contable. */
  motivo: string | null;
  metricas: Metrica[];
  enlaces: Enlace[];
}

/** Formatea un importe. Los contadores llegan como número y los importes como texto. */
function formatear(metrica: Metrica): string {
  if (metrica.unidad === "eur") {
    const numero = Number(metrica.valor);
    if (Number.isNaN(numero)) return String(metrica.valor);
    return `${numero.toLocaleString("es-ES", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })} €`;
  }
  if (metrica.unidad === "numero") return `n.º ${String(metrica.valor)}`;
  if (metrica.unidad === undefined && typeof metrica.valor === "string") {
    // Las fechas llegan como ISO en `valor`; se recortan a día, mes y año.
    return metrica.valor;
  }
  return String(metrica.valor);
}

export default function ResumenSuperficie({ superficie }: { superficie: string }) {
  const [datos, setDatos] = useState<Resumen | null>(null);
  const [error, setError] = useState(false);

  const cargar = useCallback(async () => {
    try {
      setError(false);
      setDatos(await get<Resumen>(`/api/v1/resumenes/${superficie}`));
    } catch {
      // Un resumen que no se puede leer no puede impedir entrar en la superficie: la
      // navegación es lo importante, y el resumen es un añadido. Se marca el error
      // para poder reintentar, en vez de desaparecer sin explicación.
      setDatos(null);
      setError(true);
    }
  }, [superficie]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  if (datos === null) {
    if (!error) return null;
    return (
      <section aria-label="Resumen" className="rounded-lg border border-amber-200 bg-amber-50 p-4">
        <p className="text-sm text-amber-900">
          No se pudo cargar el resumen de esta superficie.
        </p>
        <button
          type="button"
          onClick={() => void cargar()}
          className="mt-2 rounded border border-amber-300 px-2 py-1 text-xs text-amber-900 hover:bg-amber-100 focus-visible:outline-2 focus-visible:outline-amber-800"
        >
          Reintentar
        </button>
      </section>
    );
  }

  // Sin ejercicio no hay cifras que enseñar, y eso no es un fallo: es una empresa
  // recién creada. Se dice, porque un panel con la caja vacía parece un error.
  if (datos.ejercicio === null) {
    return (
      <section aria-label="Resumen" className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Resumen
        </h2>
        <p className="text-sm text-slate-600">
          Todavía no hay ningún ejercicio contable en esta empresa. El resumen aparecerá
          en cuanto se abra el primer ejercicio.
        </p>
      </section>
    );
  }

  return (
      <section aria-label="Resumen" className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Resumen del ejercicio {datos.ejercicio}
        </h2>
      <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {datos.metricas.map((metrica) => (
          <div key={metrica.clave}>
            <dt className="text-xs text-slate-500">{metrica.etiqueta}</dt>
            <dd className="text-xl font-semibold text-slate-900">
              {formatear(metrica)}
            </dd>
          </div>
        ))}
      </dl>
      {datos.enlaces.length > 0 && (
        <ul className="mt-4 flex flex-wrap gap-2 border-t border-slate-100 pt-3">
          {datos.enlaces.map((enlace) => (
            <li key={enlace.clave}>
              <Link
                href={enlace.ruta}
                className="rounded border border-slate-200 px-2 py-1 text-sm text-slate-700 hover:border-slate-400 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-slate-900"
              >
                {enlace.etiqueta}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
