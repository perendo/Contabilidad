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
    <main className="p-6 max-w-5xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Libro diario</h1>
      <form onSubmit={consultar} className="flex gap-3 mb-4 items-end flex-wrap">
        <label className="flex flex-col gap-1">
          Desde
          <input type="date" value={desde} onChange={(e) => setDesde(e.target.value)} className="border rounded px-3 py-1" />
        </label>
        <label className="flex flex-col gap-1">
          Hasta
          <input type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} className="border rounded px-3 py-1" />
        </label>
        <label className="flex flex-col gap-1">
          Estado
          <select
            value={estado}
            onChange={(e) => setEstado(e.target.value)}
            className="border rounded px-3 py-1 bg-white text-slate-900"
          >
            {OPCIONES_ESTADO.map((o) => (
              <option key={o.valor} value={o.valor}>
                {o.etiqueta}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={cargando} className="bg-blue-600 text-white rounded px-3 py-1 disabled:opacity-50">
          {cargando ? "Consultando…" : "Consultar"}
        </button>
      </form>
      {error && <p className="text-red-600 mb-4">{error}</p>}
      {diario && (
        <>
          <p className="mb-2">Total {diario.total}</p>
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b">
                <th className="text-right p-2">Nº</th>
                <th className="text-left p-2">Fecha</th>
                <th className="text-left p-2">Concepto</th>
                <th className="text-left p-2">Estado</th>
              </tr>
            </thead>
            <tbody>
              {diario.items.map((item) => (
                <tr key={item.id} className="border-b">
                  <td className="text-right p-2 font-mono">{item.numero ?? "—"}</td>
                  <td className="p-2 font-mono">{item.fecha}</td>
                  <td className="p-2">
                    <Link href={`/asientos/${item.id}`} className="text-blue-700 underline">
                      {item.concepto}
                    </Link>
                  </td>
                  <td className="p-2">{item.estado}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </main>
  );
}
