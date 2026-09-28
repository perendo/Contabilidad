"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  formatearImporte,
  listarFacturas,
  type Factura,
} from "../../../components/invoicing/api";
import { ApiError } from "../../../components/treasury/api";

const ESTADOS = ["", "borrador", "emitida", "anulada"];

export default function FacturasPage() {
  const [estado, setEstado] = useState("");
  const [items, setItems] = useState<Factura[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setError(null);
    try {
      const data = await listarFacturas({ estado: estado || undefined });
      setItems(data.items);
      setTotal(data.total);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }, [estado]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">Facturas</h1>
        <div className="flex gap-3">
          <Link
            href="/facturacion/series"
            className="bg-gray-200 rounded px-3 py-1"
          >
            Series
          </Link>
          <Link
            href="/facturacion/facturas/nueva"
            className="bg-blue-600 text-white rounded px-3 py-1"
          >
            Nueva factura
          </Link>
        </div>
      </div>

      <div className="flex items-end gap-3 mb-4">
        <label className="block">
          <span className="text-sm">Estado</span>
          <select
            value={estado}
            onChange={(e) => setEstado(e.target.value)}
            className="border rounded px-2 py-1 mt-1"
          >
            {ESTADOS.map((e) => (
              <option key={e || "todos"} value={e}>
                {e || "todos"}
              </option>
            ))}
          </select>
        </label>
        <button
          onClick={cargar}
          className="bg-gray-200 rounded px-3 py-1"
        >
          Refrescar
        </button>
        <span className="text-sm text-gray-500">{total} facturas</span>
      </div>

      {error && <p className="text-red-600 mb-4">{error}</p>}

      <table className="w-full text-sm border">
        <thead className="bg-gray-100">
          <tr>
            <th className="text-left p-2">Número</th>
            <th className="text-left p-2">Fecha</th>
            <th className="text-left p-2">Tipo</th>
            <th className="text-right p-2">Total</th>
            <th className="text-left p-2">Estado</th>
          </tr>
        </thead>
        <tbody>
          {items.map((f) => (
            <tr key={f.id} className="border-t">
              <td className="p-2">
                <Link
                  href={`/facturacion/facturas/${f.id}`}
                  className="text-blue-700 underline"
                >
                  {f.numero ?? "(sin número)"}
                </Link>
              </td>
              <td className="p-2">{f.fecha}</td>
              <td className="p-2">{f.tipo}</td>
              <td className="p-2 text-right">{formatearImporte(f.importe_total)}</td>
              <td className="p-2">{f.estado}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
