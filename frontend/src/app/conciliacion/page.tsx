"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../../components/treasury/api";
import { get, post } from "../../services/client";

interface Extracto {
  id: string;
  cuenta_id: number;
  cuenta_codigo?: string;
  fecha_inicio: string;
  fecha_fin: string;
  saldo_final: string;
  n_movimientos: number;
  estado: string;
}

interface Conciliacion {
  id: string;
  cuenta_id: number;
  cuenta_codigo?: string;
  estado: string;
  fecha_inicio: string;
  fecha_fin: string;
  saldo_banco: string;
  saldo_libros: string;
  diferencia: string;
}

export default function ConciliacionPage() {
  const [extractos, setExtractos] = useState<Extracto[]>([]);
  const [conciliaciones, setConciliaciones] = useState<Conciliacion[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [iniciandoId, setIniciandoId] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setError(null);
    try {
      const [e, c] = await Promise.all([
        get<{ items: Extracto[] }>("/api/v1/extractos"),
        get<{ items: Conciliacion[] }>("/api/v1/conciliaciones"),
      ]);
      setExtractos(e.items || []);
      setConciliaciones(c.items || []);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  // Iniciar sesión de conciliación a partir de un extracto importado
  async function iniciarConciliacion(extracto: Extracto) {
    setError(null);
    setIniciandoId(extracto.id);
    try {
      const nueva = await post<Conciliacion>("/api/v1/conciliaciones", {
        cuenta_id: extracto.cuenta_id,
        extracto_id: extracto.id,
        fecha_inicio: extracto.fecha_inicio,
        fecha_fin: extracto.fecha_fin,
      });
      await cargar();
      if (nueva?.id) {
        window.location.href = `/conciliacion/${nueva.id}`;
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError(err instanceof Error ? err.message : "Error al iniciar la conciliación");
      }
    } finally {
      setIniciandoId(null);
    }
  }

  return (
    <main className="p-6 max-w-5xl mx-auto space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-6 h-6 text-blue-600">
              <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
            </svg>
            Conciliación Bancaria
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Importa extractos bancarios (Norma 43, Excel, CSV) e inicia la sesión de cruce y casación.
          </p>
        </div>
        <Link
          href="/conciliacion/importar"
          className="bg-blue-600 hover:bg-blue-700 text-white rounded-lg px-4 py-2 font-semibold text-xs shadow-sm transition-colors flex items-center gap-1.5"
        >
          <span>+ Importar extracto</span>
        </Link>
      </div>

      {error && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-rose-700 text-xs font-medium flex items-center gap-2">
          <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 text-rose-600 shrink-0">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clipRule="evenodd" />
          </svg>
          <span>{error}</span>
        </div>
      )}

      {/* SECCIÓN 1: EXTRACTOS BANCARIOS IMPORTADOS */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-bold text-sm text-slate-800 uppercase tracking-wider flex items-center gap-2">
            <span>Extractos Bancarios Importados</span>
            <span className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full font-mono font-semibold">
              {extractos.length}
            </span>
          </h2>
        </div>

        {extractos.length === 0 ? (
          <div className="p-6 bg-slate-50 border border-slate-200 rounded-xl text-center space-y-2">
            <p className="text-xs text-slate-500">No hay extractos bancarios importados en este ejercicio.</p>
            <Link
              href="/conciliacion/importar"
              className="inline-block px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded text-xs font-semibold"
            >
              Importar mi primer extracto
            </Link>
          </div>
        ) : (
          <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
            <table className="w-full border-collapse text-xs">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold">
                <tr>
                  <th className="text-left p-3">Rango Fechas</th>
                  <th className="text-right p-3">Saldo final</th>
                  <th className="text-right p-3">Nº Movimientos</th>
                  <th className="text-left p-3">Estado</th>
                  <th className="text-right p-3">Acción</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {extractos.map((e) => {
                  const tieneConciliacion = conciliaciones.some(
                    (c) => String(c.cuenta_id) === String(e.cuenta_id)
                  );
                  return (
                    <tr key={e.id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="p-3 font-mono font-medium text-slate-900">
                        {e.fecha_inicio} → {e.fecha_fin}
                      </td>
                      <td className="text-right p-3 font-mono font-bold text-slate-900">
                        {e.saldo_final} €
                      </td>
                      <td className="text-right p-3 font-mono text-slate-700">
                        {e.n_movimientos}
                      </td>
                      <td className="p-3">
                        <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-blue-50 text-blue-700 border border-blue-200 uppercase">
                          {e.estado}
                        </span>
                      </td>
                      <td className="p-3 text-right">
                        <button
                          type="button"
                          onClick={() => iniciarConciliacion(e)}
                          disabled={iniciandoId === e.id}
                          className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg font-bold text-xs shadow-sm transition-colors disabled:opacity-50 inline-flex items-center gap-1"
                        >
                          {iniciandoId === e.id ? (
                            "Iniciando..."
                          ) : (
                            <>
                              <span>Conciliar extracto</span>
                              <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5">
                                <path fillRule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clipRule="evenodd" />
                              </svg>
                            </>
                          )}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* SECCIÓN 2: SESIONES DE CONCILIACIÓN */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-bold text-sm text-slate-800 uppercase tracking-wider flex items-center gap-2">
            <span>Sesiones de Conciliación Activas</span>
            <span className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full font-mono font-semibold">
              {conciliaciones.length}
            </span>
          </h2>
        </div>

        {conciliaciones.length === 0 ? (
          <div className="p-6 bg-slate-50 border border-slate-200 rounded-xl text-center space-y-1">
            <p className="text-xs text-slate-600 font-medium">No hay ninguna sesión de conciliación abierta todavía.</p>
            <p className="text-[11px] text-slate-500">
              Pulsa en el botón verde <strong>«Conciliar extracto»</strong> arriba para iniciar la casación del extracto importado.
            </p>
          </div>
        ) : (
          <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
            <table className="w-full border-collapse text-xs">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold">
                <tr>
                  <th className="text-left p-3">Cuenta ID / Banco</th>
                  <th className="text-left p-3">Estado</th>
                  <th className="text-right p-3">Saldo Banco</th>
                  <th className="text-right p-3">Saldo Libros</th>
                  <th className="text-right p-3">Diferencia</th>
                  <th className="text-right p-3">Acción</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {conciliaciones.map((c) => {
                  const cuadrada = c.diferencia === "0.0000" || Number(c.diferencia) === 0;
                  return (
                    <tr key={c.id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="p-3 font-mono font-semibold text-slate-900">
                        Cuenta #{c.cuenta_id}
                      </td>
                      <td className="p-3">
                        <span className={`px-2 py-0.5 rounded text-[11px] font-bold uppercase ${
                          c.estado === "cerrada"
                            ? "bg-slate-100 text-slate-700 border border-slate-300"
                            : "bg-emerald-50 text-emerald-800 border border-emerald-300"
                        }`}>
                          {c.estado}
                        </span>
                      </td>
                      <td className="text-right p-3 font-mono text-slate-900">
                        {c.saldo_banco ?? "0.00"} €
                      </td>
                      <td className="text-right p-3 font-mono text-slate-900">
                        {c.saldo_libros ?? "0.00"} €
                      </td>
                      <td className="text-right p-3 font-mono font-bold">
                        <span className={cuadrada ? "text-emerald-700" : "text-amber-700"}>
                          {c.diferencia} €
                        </span>
                      </td>
                      <td className="p-3 text-right">
                        <Link
                          href={`/conciliacion/${c.id}`}
                          className="px-3.5 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-bold text-xs shadow-sm transition-colors inline-flex items-center gap-1"
                        >
                          <span>Abrir y Casar</span>
                          <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5">
                            <path fillRule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clipRule="evenodd" />
                          </svg>
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
