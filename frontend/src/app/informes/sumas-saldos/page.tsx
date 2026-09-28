"use client";

import { useState } from "react";

import { ApiError } from "../../../components/treasury/api";
import { get } from "../../../services/client";
import TrialBalanceTable from "../../../components/reports/TrialBalanceTable";

interface Balance {
  total_debe: string;
  total_haber: string;
  cuadra: boolean;
  items: { code: string; name: string; debe: string; haber: string; saldo: string }[];
}

export default function SumasSaldosPage() {
  const [desde, setDesde] = useState("2026-01-01");
  const [hasta, setHasta] = useState("2026-12-31");
  const [nivel, setNivel] = useState("4");
  const [balance, setBalance] = useState<Balance | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);

  async function generar(evento: React.FormEvent) {
    evento.preventDefault();
    setError(null);
    setCargando(true);
    try {
      const params = new URLSearchParams({
        date_from: desde,
        date_to: hasta,
        level: nivel,
      });
      setBalance(await get<Balance>(`/api/v1/reports/trial-balance?${params}`));
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    } finally {
      setCargando(false);
    }
  }

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Balance de sumas y saldos</h1>
      <form onSubmit={generar} className="flex gap-3 mb-4 items-end">
        <label className="flex flex-col gap-1">
          Desde
          <input type="date" value={desde} onChange={(e) => setDesde(e.target.value)} className="border rounded px-3 py-1" />
        </label>
        <label className="flex flex-col gap-1">
          Hasta
          <input type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} className="border rounded px-3 py-1" />
        </label>
        <label className="flex flex-col gap-1">
          Nivel
          <input type="number" min={1} value={nivel} onChange={(e) => setNivel(e.target.value)} className="border rounded px-3 py-1 w-20" />
        </label>
        <button type="submit" disabled={cargando} className="bg-blue-600 text-white rounded px-3 py-1 disabled:opacity-50">
          {cargando ? "Generando…" : "Generar"}
        </button>
      </form>
      {error && <p className="text-red-600 mb-4">{error}</p>}
      {balance && (
        <>
          <p className={balance.cuadra ? "text-emerald-700 mb-2" : "text-red-600 mb-2"}>
            Total debe {balance.total_debe} · Total haber {balance.total_haber} ·{" "}
            {balance.cuadra ? "Cuadra" : "NO CUADRA"}
          </p>
          <TrialBalanceTable items={balance.items} />
        </>
      )}
    </main>
  );
}
