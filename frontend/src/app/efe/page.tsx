"use client";

import { useCallback, useEffect, useState } from "react";

import { EfeView } from "../../components/reporting/EfeView";
import { obtenerEfe, type EfeReport } from "../../components/reporting/api";
import { ApiError } from "../../components/treasury/api";

export default function EfePage() {
  const [ejercicio, setEjercicio] = useState(2026);
  const [modo, setModo] = useState("provisional");
  const [report, setReport] = useState<EfeReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setError(null);
    try {
      setReport(await obtenerEfe(ejercicio, { modo }));
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }, [ejercicio, modo]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  return (
    <main className="p-6 max-w-4xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Estado de Flujos de Efectivo</h1>
      <div className="flex items-end gap-3 mb-4">
        <label className="block">
          <span className="text-sm">Ejercicio</span>
          <input
            type="number"
            value={ejercicio}
            onChange={(e) => setEjercicio(Number(e.target.value))}
            className="border rounded px-3 py-1 mt-1 w-32"
          />
        </label>
        <select
          value={modo}
          onChange={(e) => setModo(e.target.value)}
          className="border rounded px-2 py-1"
        >
          <option value="provisional">provisional</option>
          <option value="oficial">oficial</option>
        </select>
      </div>
      {error && <p className="text-red-600 mb-4">{error}</p>}
      <div className="border rounded p-4">
        {report ? <EfeView report={report} /> : <p>Cargando…</p>}
      </div>
    </main>
  );
}