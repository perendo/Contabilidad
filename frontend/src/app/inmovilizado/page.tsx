"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  listarActivos,
  type Activo,
} from "../../components/inmovilizado/api";

export default function InmovilizadoPage() {
  const [items, setItems] = useState<Activo[]>([]);
  const [total, setTotal] = useState(0);
  const [estado, setEstado] = useState("");
  const [error, setError] = useState<string | null>(null);

  const consultar = useCallback(async () => {
    setError(null);
    try {
      const cuerpo = await listarActivos({ estado: estado || undefined });
      setItems(cuerpo.items);
      setTotal(cuerpo.total);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    }
  }, [estado]);

  useEffect(() => {
    consultar();
  }, [consultar]);

  return (
    <main className="p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">Activos del inmovilizado</h1>
        <Link
          href="/inmovilizado/alta"
          className="bg-blue-600 text-white rounded px-4 py-2"
        >
          Alta de activo
        </Link>
      </div>

      <div className="flex items-center gap-3 mb-4">
        <select
          value={estado}
          onChange={(e) => setEstado(e.target.value)}
          className="border rounded px-3 py-1"
        >
          <option value="">Todos los estados</option>
          <option value="en_uso">En uso</option>
          <option value="dado_de_baja">Dado de baja</option>
        </select>
        <Link
          href="/inmovilizado/amortizaciones"
          className="text-blue-600 underline text-sm"
        >
          Amortizaciones generadas
        </Link>
      </div>

      {error && <p className="text-red-600 mb-4">{error}</p>}

      <p className="text-sm text-gray-600 mb-2">Total: {total}</p>

      <table className="w-full text-sm border rounded">
        <thead>
          <tr className="text-left bg-gray-100">
            <th className="p-2">Nº</th>
            <th className="p-2">Descripción</th>
            <th className="p-2">Estado</th>
            <th className="p-2">Coste</th>
            <th className="p-2">Amortizado</th>
          </tr>
        </thead>
        <tbody>
          {items.map((a) => (
            <tr key={a.id} className="border-t">
              <td className="p-2">
                <Link
                  className="text-blue-600 underline font-mono"
                  href={`/inmovilizado/${a.id}`}
                >
                  {a.numero_activo}
                </Link>
              </td>
              <td className="p-2">{a.descripcion}</td>
              <td className="p-2">{a.estado}</td>
              <td className="p-2 font-mono">{a.coste_amortizable}</td>
              <td className="p-2 font-mono">{a.amortizado_acumulado ?? "0.0000"}</td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td colSpan={5} className="p-2 text-gray-500">
                Sin activos.{" "}
                <Link className="text-blue-600 underline" href="/inmovilizado/alta">
                  Crea el primero
                </Link>
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </main>
  );
}