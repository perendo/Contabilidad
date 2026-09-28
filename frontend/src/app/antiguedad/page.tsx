"use client";

import { useState } from "react";

import { ApiError } from "../../components/treasury/api";
import { get } from "../../services/client";

interface FilaAntiguedad {
  tercero_id: string;
  nombre: string;
  rango_30: string;
  rango_60: string;
  rango_90: string;
  rango_90mas: string;
  total: string;
}

interface Informe {
  fecha_corte: string;
  total: string;
  items: FilaAntiguedad[];
}

export default function AntiguedadPage() {
  const [fechaCorte, setFechaCorte] = useState("2026-06-30");
  const [informe, setInforme] = useState<Informe | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);

  async function consultar(evento: React.FormEvent) {
    evento.preventDefault();
    setError(null);
    setCargando(true);
    try {
      const params = new URLSearchParams({ fecha_corte: fechaCorte });
      setInforme(await get<Informe>(`/api/v1/antiguedad?${params}`));
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    } finally {
      setCargando(false);
    }
  }

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Antigüedad de saldos</h1>
      <form onSubmit={consultar} className="flex gap-3 mb-4 items-end">
        <label className="flex flex-col gap-1">
          Fecha de corte
          <input type="date" value={fechaCorte} onChange={(e) => setFechaCorte(e.target.value)} className="border rounded px-3 py-1" />
        </label>
        <button type="submit" disabled={cargando} className="bg-blue-600 text-white rounded px-3 py-1 disabled:opacity-50">
          {cargando ? "Calculando…" : "Calcular"}
        </button>
      </form>
      {error && <p className="text-red-600 mb-4">{error}</p>}
      {informe && (
        <>
          <p className="mb-2">Total {informe.total}</p>
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b">
                <th className="text-left p-2">Tercero</th>
                <th className="text-right p-2">0-30</th>
                <th className="text-right p-2">31-60</th>
                <th className="text-right p-2">61-90</th>
                <th className="text-right p-2">&gt;90</th>
                <th className="text-right p-2">Total</th>
              </tr>
            </thead>
            <tbody>
              {informe.items.map((f) => (
                <tr key={f.tercero_id} className="border-b">
                  <td className="p-2">{f.nombre}</td>
                  <td className="text-right p-2 font-mono">{f.rango_30}</td>
                  <td className="text-right p-2 font-mono">{f.rango_60}</td>
                  <td className="text-right p-2 font-mono">{f.rango_90}</td>
                  <td className="text-right p-2 font-mono">{f.rango_90mas}</td>
                  <td className="text-right p-2 font-mono">{f.total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </main>
  );
}
