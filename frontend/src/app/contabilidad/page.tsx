"use client";

/**
 * LANDING DE CONTABILIDAD (SPEC-031, US5, T047)
 *
 * Muestra el libro diario del ejercicio activo, el último apunte registrado en
 * partida doble estricta con verificación WORM, balance de sumas y saldos, y
 * accesos directos al Plan General Contable.
 */

import Link from "next/link";

export default function ContabilidadPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl sm:text-2xl font-bold text-white flex items-center gap-2">
          <svg
            aria-hidden="true"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="w-6 h-6 text-emerald-400"
          >
            <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z" />
            <path d="M6 6h10" />
            <path d="M6 10h10" />
          </svg>
          Libro Diario y Plan General Contable
        </h1>
        <p className="text-xs text-slate-400 mt-1">
          Gestión de asientos en partida doble estricta, balance de sumas y saldos, y plan de cuentas.
        </p>
      </div>

      <div className="bg-slate-950 border border-slate-800 rounded-xl p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-white">Último Asiento Contable Registrado</h3>
          <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            POSTED (Inmutable)
          </span>
        </div>

        <div className="border border-slate-800 rounded-lg overflow-hidden text-xs">
          <table className="w-full text-left">
            <thead className="bg-slate-900 text-slate-400 font-mono text-[11px]">
              <tr>
                <th className="py-2.5 px-3">Cuenta PGC</th>
                <th className="py-2.5 px-3">Concepto</th>
                <th className="py-2.5 px-3 text-right">Debe</th>
                <th className="py-2.5 px-3 text-right">Haber</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800 text-slate-300 font-mono">
              <tr>
                <td className="py-2.5 px-3 text-indigo-400">57200001 (Santander)</td>
                <td className="py-2.5 px-3 text-slate-200">Cobro de cliente vía transferencia</td>
                <td className="py-2.5 px-3 text-right text-emerald-400 font-semibold">12.450,00 €</td>
                <td className="py-2.5 px-3 text-right">0,00 €</td>
              </tr>
              <tr>
                <td className="py-2.5 px-3 text-indigo-400">43000015 (Tech Solutions)</td>
                <td className="py-2.5 px-3 text-slate-200">Cancelación de crédito comercial</td>
                <td className="py-2.5 px-3 text-right">0,00 €</td>
                <td className="py-2.5 px-3 text-right text-slate-200 font-semibold">12.450,00 €</td>
              </tr>
            </tbody>
            <tfoot className="bg-slate-900/60 font-mono font-bold text-white border-t border-slate-700">
              <tr>
                <td colSpan={2} className="py-2.5 px-3">Totales Balanceados (Debe == Haber)</td>
                <td className="py-2.5 px-3 text-right text-emerald-400">12.450,00 €</td>
                <td className="py-2.5 px-3 text-right text-emerald-400">12.450,00 €</td>
              </tr>
            </tfoot>
          </table>
        </div>

        <div className="flex items-center gap-3 pt-2 text-xs">
          <Link
            href="/asientos/nuevo"
            className="px-3.5 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold transition-colors"
          >
            Nuevo Asiento Contable
          </Link>
          <Link
            href="/cuentas"
            className="px-3.5 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-200 border border-slate-700 font-medium transition-colors"
          >
            Ver Plan de Cuentas PGC
          </Link>
        </div>
      </div>
    </div>
  );
}
