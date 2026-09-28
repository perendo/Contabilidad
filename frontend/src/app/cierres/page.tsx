"use client";

import Link from "next/link";

export default function CierresPage() {
  return (
    <main className="p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Cierres</h1>
        <p className="text-sm text-gray-500">
          Cierres intermedios, cierre anual y reaperturas controladas
        </p>
      </div>

      <section className="grid gap-4 md:grid-cols-3">
        <Link
          href="/cierres/intermedio"
          className="rounded border bg-white p-4 hover:bg-gray-50"
        >
          <h2 className="font-semibold text-blue-700">Cierre intermedio</h2>
          <p className="mt-1 text-sm text-gray-600">
            Cierra un mes o un trimestre: genera el balance de comprobacion y
            bloquea la contabilizacion del periodo.
          </p>
        </Link>

        <Link
          href="/cierres/anual"
          className="rounded border bg-white p-4 hover:bg-gray-50"
        >
          <h2 className="font-semibold text-blue-700">Cierre anual</h2>
          <p className="mt-1 text-sm text-gray-600">
            Regulariza los grupos 6 y 7, salda el balance, bloquea el ejercicio y
            genera la apertura del siguiente.
          </p>
        </Link>

        <Link
          href="/cierres/reaperturas"
          className="rounded border bg-white p-4 hover:bg-gray-50"
        >
          <h2 className="font-semibold text-blue-700">Reaperturas</h2>
          <p className="mt-1 text-sm text-gray-600">
            Solicita, aprueba y regulariza la reapertura de un periodo cerrado
            mediante un asiento rectificativo.
          </p>
        </Link>
      </section>
    </main>
  );
}
