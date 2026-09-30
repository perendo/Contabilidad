"use client";

/**
 * LANDING DE FACTURACIÓN (SPEC-031, US5, T048)
 */

import Link from "next/link";

export default function FacturacionPage() {
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-white flex items-center gap-2">
            <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-6 h-6 text-blue-400">
              <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
              <path d="M14 2v4a2 2 0 0 0 2 2h4" />
              <path d="M8 13h2" />
              <path d="M14 13h2" />
              <path d="M8 17h2" />
              <path d="M14 17h2" />
            </svg>
            Facturación Emitida y Recibida
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Series de facturación, emisión con hash Veri*factu, control de rectificativas y cálculo de bases imponibles.
          </p>
        </div>

        <div className="flex items-center gap-2 text-xs">
          <Link
            href="/facturas/emitidas/nueva"
            className="px-3.5 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold transition-all"
          >
            Emitir Factura
          </Link>
          <Link
            href="/facturas/recibidas/nueva"
            className="px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-all font-medium"
          >
            Registrar Gasto
          </Link>
        </div>
      </div>
    </div>
  );
}
