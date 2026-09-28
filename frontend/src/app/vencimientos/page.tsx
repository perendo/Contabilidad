"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../../components/treasury/api";
import { get, post } from "../../services/client";

interface Vencimiento {
  id: string;
  recibo_num: string;
  tipo: string;
  fecha_vencimiento: string;
  importe: string;
  saldo_pendiente: string;
  estado: string;
}

export default function VencimientosPage() {
  const [items, setItems] = useState<Vencimiento[]>([]);
  const [estado, setEstado] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [cobrando, setCobrando] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setError(null);
    try {
      const params = new URLSearchParams();
      if (estado) params.set("estado", estado);
      const cuerpo = await get<{ items: Vencimiento[] }>(`/api/v1/vencimientos?${params}`);
      setItems(cuerpo.items);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }, [estado]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  async function cobrar(v: Vencimiento) {
    setError(null);
    setCobrando(v.id);
    try {
      await post(`/api/v1/vencimientos/${v.id}/cobrar`, {
        fecha: new Date().toISOString().slice(0, 10),
        importe: v.saldo_pendiente,
      });
      await cargar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    } finally {
      setCobrando(null);
    }
  }

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Vencimientos</h1>
      <select value={estado} onChange={(e) => setEstado(e.target.value)} className="border rounded px-2 py-1 mb-4">
        <option value="">Todos</option>
        <option value="pendiente">Pendientes</option>
        <option value="parcial">Parciales</option>
        <option value="cobrado">Cobrados</option>
        <option value="remesado">Remesados</option>
      </select>
      {error && <p className="text-red-600 mb-4">{error}</p>}
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b">
            <th className="text-left p-2">Recibo</th>
            <th className="text-left p-2">Vencimiento</th>
            <th className="text-right p-2">Importe</th>
            <th className="text-right p-2">Pendiente</th>
            <th className="text-left p-2">Estado</th>
            <th className="p-2" />
          </tr>
        </thead>
        <tbody>
          {items.map((v) => (
            <tr key={v.id} className="border-b">
              <td className="p-2 font-mono">{v.recibo_num}</td>
              <td className="p-2 font-mono">{v.fecha_vencimiento}</td>
              <td className="text-right p-2 font-mono">{v.importe}</td>
              <td className="text-right p-2 font-mono">{v.saldo_pendiente}</td>
              <td className="p-2">{v.estado}</td>
              <td className="p-2 text-right">
                {v.estado !== "cobrado" && v.estado !== "remesado" && (
                  <button
                    onClick={() => cobrar(v)}
                    disabled={cobrando === v.id}
                    className="bg-blue-600 text-white rounded px-3 py-1 disabled:opacity-50"
                  >
                    {cobrando === v.id ? "Cobrando…" : "Cobrar"}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
