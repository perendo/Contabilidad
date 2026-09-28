"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  listarAmortizaciones,
  reabrirAmortizacion,
  type Generada,
} from "../../../components/inmovilizado/api";

export default function AmortizacionesPage() {
  const [items, setItems] = useState<Generada[]>([]);
  const [total, setTotal] = useState(0);
  const [ejercicio, setEjercicio] = useState("");
  const [periodo, setPeriodo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState<string | null>(null);

  const consultar = useCallback(async () => {
    setError(null);
    try {
      const cuerpo = await listarAmortizaciones({
        ejercicio: ejercicio ? Number(ejercicio) : undefined,
        periodo: periodo ? Number(periodo) : undefined,
      });
      setItems(cuerpo.items);
      setTotal(cuerpo.total);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    }
  }, [ejercicio, periodo]);

  useEffect(() => {
    consultar();
  }, [consultar]);

  async function reabrir(g: Generada) {
    setError(null);
    setAviso(null);
    setOcupado(g.id);
    try {
      const r = await reabrirAmortizacion(g.id, `Reapertura ${g.ejercicio}-${g.periodo}`);
      setAviso(
        `Período ${g.ejercicio}-${g.periodo} reabierto (REVERSAL nº ${r.numero_reversal}).`
      );
      await consultar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    } finally {
      setOcupado(null);
    }
  }

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">Amortizaciones generadas</h1>
        <Link href="/inmovilizado" className="text-blue-600 underline text-sm">
          Volver a activos
        </Link>
      </div>

      <div className="flex items-end gap-3 mb-4 text-sm">
        <label className="block">
          <span>Ejercicio</span>
          <input
            type="number"
            value={ejercicio}
            onChange={(e) => setEjercicio(e.target.value)}
            className="border rounded px-3 py-1 mt-1 w-28"
          />
        </label>
        <label className="block">
          <span>Período (mes)</span>
          <input
            type="number"
            min={1}
            max={12}
            value={periodo}
            onChange={(e) => setPeriodo(e.target.value)}
            className="border rounded px-3 py-1 mt-1 w-28"
          />
        </label>
        <button
          onClick={() => {
            setEjercicio("");
            setPeriodo("");
          }}
          className="bg-gray-200 rounded px-4 py-2"
        >
          Limpiar filtros
        </button>
      </div>

      {error && <p className="text-red-600 mb-4">{error}</p>}
      {aviso && <p className="text-emerald-700 mb-4">{aviso}</p>}

      <p className="text-sm text-gray-600 mb-2">Total: {total}</p>

      <table className="w-full text-sm border rounded">
        <thead>
          <tr className="text-left bg-gray-100">
            <th className="p-2">Período</th>
            <th className="p-2">Activo</th>
            <th className="p-2">Cuota</th>
            <th className="p-2">Asiento</th>
            <th className="p-2">Estado</th>
            <th className="p-2">Acciones</th>
          </tr>
        </thead>
        <tbody>
          {items.map((g) => (
            <tr key={g.id} className="border-t">
              <td className="p-2 font-mono">
                {g.ejercicio}-{String(g.periodo).padStart(2, "0")}
              </td>
              <td className="p-2">
                <Link
                  className="text-blue-600 underline"
                  href={`/inmovilizado/${g.activo_id}`}
                >
                  {g.activo_id.slice(0, 8)}…
                </Link>
              </td>
              <td className="p-2 font-mono">{g.cuota}</td>
              <td className="p-2 font-mono">{g.asiento_id.slice(0, 8)}…</td>
              <td className="p-2">{g.reabierta ? "Reabierta" : "Vigente"}</td>
              <td className="p-2">
                {!g.reabierta && (
                  <button
                    onClick={() => reabrir(g)}
                    disabled={ocupado !== null}
                    className="text-blue-600 underline disabled:opacity-50"
                  >
                    {ocupado === g.id ? "Reabriendo…" : "Reabrir"}
                  </button>
                )}
              </td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td colSpan={6} className="p-2 text-gray-500">
                Sin amortizaciones generadas.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </main>
  );
}