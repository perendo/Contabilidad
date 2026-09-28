"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ApiError,
  historialPorAsiento,
  listarTipos,
  type TipoCambio,
} from "@/components/forex/api";

export default function HistorialTiposPage() {
  const [items, setItems] = useState<TipoCambio[]>([]);
  const [asientoId, setAsientoId] = useState("");
  const [aviso, setAviso] = useState<string | null>(null);

  async function consultarTodos() {
    setAviso(null);
    try {
      setItems((await listarTipos()).items);
    } catch (error) {
      setAviso(error instanceof ApiError ? error.message : "No se pudo consultar el historial");
    }
  }

  async function consultarPorAsiento() {
    setAviso(null);
    try {
      const resultado = await historialPorAsiento(asientoId);
      setItems(resultado.items);
    } catch (error) {
      setAviso(error instanceof ApiError ? error.message : "Asiento sin tipo asociado");
      setItems([]);
    }
  }

  useEffect(() => {
    consultarTodos();
  }, []);

  return (
    <main className="p-6 max-w-4xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">
        Historial de tipos de cambio{" "}
        <Link className="text-sm text-blue-600 underline" href="/divisas/tipos">
          tipos
        </Link>
      </h1>

      <section className="border rounded p-4 mb-4">
        <h2 className="font-medium mb-2">Consulta por asiento</h2>
        <div className="flex gap-2">
          <input
            className="border rounded p-1 flex-1"
            value={asientoId}
            onChange={(e) => setAsientoId(e.target.value)}
            placeholder="id del asiento en divisa"
          />
          <button
            className="bg-slate-800 text-white rounded px-3 py-1"
            onClick={consultarPorAsiento}
            disabled={!asientoId}
          >
            Consultar
          </button>
        </div>
        {aviso && <p className="mt-2 text-sm text-amber-700">{aviso}</p>}
      </section>

      <section className="border rounded p-4">
        <h2 className="font-medium mb-2">Histórico por divisa y fecha</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left border-b">
              <th>Divisa</th>
              <th>Fecha</th>
              <th>Ratio</th>
              <th>Usos</th>
              <th>Estado</th>
            </tr>
          </thead>
          <tbody>
            {items.map((tipo) => (
              <tr key={tipo.id} className="border-b">
                <td>{tipo.divisa}</td>
                <td>{tipo.fecha}</td>
                <td>{tipo.ratio}</td>
                <td>{tipo.usos_posteados}</td>
                <td>{tipo.sellado ? "sellado" : "editable"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}