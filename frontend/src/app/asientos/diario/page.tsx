"use client";

import Link from "next/link";
import { useState } from "react";
import { ApiError } from "../../../components/treasury/api";
import { get } from "../../../services/client";

interface ItemDiario {
  id: string;
  numero: number | null;
  fecha: string;
  concepto: string;
  estado: string;
}

interface Diario {
  total: number;
  page: number;
  page_size: number;
  items: ItemDiario[];
}

/**
 * Filtro de estado. Por defecto (opción vacía) el backend devuelve
 * POSTED+CANCELLED, que es el contrato histórico del libro: el borrador no forma
 * parte de él. Las opciones se envían como `?estado=`, y un valor desconocido
 * contesta 422 `estado_desconocido` en vez de devolver cero filas en silencio.
 */
const OPCIONES_ESTADO = [
  { valor: "", etiqueta: "Publicados y anulados" },
  { valor: "DRAFT", etiqueta: "Borradores" },
  { valor: "POSTED", etiqueta: "Publicados" },
  { valor: "CANCELLED", etiqueta: "Anulados" },
  { valor: "DRAFT,POSTED,CANCELLED", etiqueta: "Todos" },
];

export default function DiarioPage() {
  const [desde, setDesde] = useState("2026-01-01");
  const [hasta, setHasta] = useState("2026-12-31");
  const [estado, setEstado] = useState("");
  const [diario, setDiario] = useState<Diario | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);

  async function consultar(evento: React.FormEvent) {
    evento.preventDefault();
    setError(null);
    setCargando(true);
    try {
      const params = new URLSearchParams({ date_from: desde, date_to: hasta });
      if (estado) params.set("estado", estado);
      setDiario(await get<Diario>(`/api/v1/journal/entries?${params}`));
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    } finally {
      setCargando(false);
    }
  }

  return (
    <main className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-6 h-6 text-emerald-600">
              <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z" />
              <path d="M6 6h10" />
              <path d="M6 10h10" />
            </svg>
            Libro Diario
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Consulta los asientos registrados, borradores y anulaciones del ejercicio.
          </p>
        </div>

        <Link
          href="/asientos/nuevo"
          className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-bold shadow-sm transition-colors flex items-center gap-1.5"
        >
          <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
            <path fillRule="evenodd" d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z" clipRule="evenodd" />
          </svg>
          <span>Nuevo Asiento</span>
        </Link>
      </div>

      <form onSubmit={consultar} className="flex gap-3 mb-4 items-end flex-wrap bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
        <label className="flex flex-col gap-1 text-xs font-semibold text-slate-700">
          Desde
          <input type="date" value={desde} onChange={(e) => setDesde(e.target.value)} className="border rounded px-3 py-1.5 text-xs text-slate-900" />
        </label>
        <label className="flex flex-col gap-1 text-xs font-semibold text-slate-700">
          Hasta
          <input type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} className="border rounded px-3 py-1.5 text-xs text-slate-900" />
        </label>
        <label className="flex flex-col gap-1 text-xs font-semibold text-slate-700">
          Estado
          <select
            value={estado}
            onChange={(e) => setEstado(e.target.value)}
            className="border rounded px-3 py-1.5 bg-white text-xs text-slate-900"
          >
            {OPCIONES_ESTADO.map((o) => (
              <option key={o.valor} value={o.valor}>
                {o.etiqueta}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={cargando} className="bg-blue-600 hover:bg-blue-700 text-white rounded px-4 py-1.5 text-xs font-bold transition-colors shadow-sm disabled:opacity-50">
          {cargando ? "Consultando…" : "Consultar"}
        </button>
      </form>

      {error && (
        <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-rose-700 text-xs font-medium">
          {error}
        </div>
      )}

      {diario && (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-600 font-semibold px-1">
            <span>Total asientos encontrados: {diario.total}</span>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
            <table className="w-full border-collapse text-xs">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold">
                <tr>
                  <th className="text-right p-3">Nº Asiento</th>
                  <th className="text-left p-3">Fecha</th>
                  <th className="text-left p-3">Concepto</th>
                  <th className="text-left p-3">Estado</th>
                  <th className="text-right p-3">Acción</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {diario.items.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="text-right p-3 font-mono font-bold text-slate-900">{item.numero ?? "—"}</td>
                    <td className="p-3 font-mono text-slate-700">{item.fecha}</td>
                    <td className="p-3 font-medium text-slate-900">
                      <Link href={`/asientos/${item.id}`} className="text-blue-600 hover:underline">
                        {item.concepto}
                      </Link>
                    </td>
                    <td className="p-3">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                        item.estado === "POSTED"
                          ? "bg-emerald-50 text-emerald-800 border border-emerald-300"
                          : item.estado === "DRAFT"
                          ? "bg-amber-50 text-amber-800 border border-amber-300"
                          : "bg-rose-50 text-rose-800 border border-rose-300"
                      }`}>
                        {item.estado}
                      </span>
                    </td>
                    <td className="p-3 text-right">
                      <Link href={`/asientos/${item.id}`} className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded text-xs font-semibold transition-colors">
                        Ver detalle →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </main>
  );
}
