"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { PlanTree } from "@/components/acct/PlanTree";
import { obtenerArbolCuentas, type CuentaNodo } from "@/services/acct/api";

export default function CuentasPage() {
  const [nodos, setNodos] = useState<CuentaNodo[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function cargarArbol() {
      try {
        setCargando(true);
        const data = await obtenerArbolCuentas();
        setNodos(data.nodos || []);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Error al cargar el plan de cuentas");
      } finally {
        setCargando(false);
      }
    }
    cargarArbol();
  }, []);

  if (cargando) {
    return (
      <div className="p-6 text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
        <p className="mt-2 text-slate-300 text-sm">Cargando plan de cuentas...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 text-center text-red-400">
        <p>{error}</p>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-6xl">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
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
            Plan General Contable
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Árbol jerárquico de cuentas, grupos, subgrupos y subcuentas apuntables (Nivel ≥ 4).
          </p>
        </div>

        <Link
          href="/cuentas/nueva"
          className="px-4 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-sm flex items-center gap-2 transition-colors shadow-sm"
        >
          <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
            <path d="M10.75 4.75a.75.75 0 0 0-1.5 0v4.5h-4.5a.75.75 0 0 0 0 1.5h4.5v4.5a.75.75 0 0 0 1.5 0v-4.5h4.5a.75.75 0 0 0 0-1.5h-4.5v-4.5Z" />
          </svg>
          Nueva Cuenta / Subcuenta
        </Link>
      </div>

      <div className="bg-white rounded-xl shadow-lg border border-slate-300 p-4 text-slate-900">
        <PlanTree nodos={nodos} />
      </div>
    </div>
  );
}
