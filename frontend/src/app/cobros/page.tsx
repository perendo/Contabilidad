"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../../components/treasury/api";
import { get } from "../../services/client";

interface Vencimiento {
  id: string;
  recibo_num: string;
  estado: string;
  acumulado: string;
  importe: string;
}

interface Cobro {
  id: string;
  fecha: string;
  importe: string;
  cuenta_tesoreria: string;
}

export default function CobrosPage() {
  const [vencimientos, setVencimientos] = useState<Vencimiento[]>([]);
  const [seleccionado, setSeleccionado] = useState<string | null>(null);
  const [cobros, setCobros] = useState<Cobro[]>([]);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    try {
      const cuerpo = await get<{ items: Vencimiento[] }>("/api/v1/vencimientos");
      setVencimientos(cuerpo.items.filter((v) => v.acumulado !== "0.0000"));
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  async function verCobros(id: string) {
    setSeleccionado(id);
    try {
      const cuerpo = await get<{ items: Cobro[] }>(`/api/v1/vencimientos/${id}/cobros`);
      setCobros(cuerpo.items);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Cobros y pagos</h1>
      {error && <p className="text-red-600 mb-4">{error}</p>}
      <table className="w-full border-collapse text-sm mb-6">
        <thead>
          <tr className="border-b">
            <th className="text-left p-2">Recibo</th>
            <th className="text-right p-2">Importe</th>
            <th className="text-right p-2">Cobrado</th>
            <th className="text-left p-2">Estado</th>
          </tr>
        </thead>
        <tbody>
          {vencimientos.map((v) => (
            <tr
              key={v.id}
              className={`border-b cursor-pointer ${seleccionado === v.id ? "bg-slate-100" : ""}`}
              onClick={() => verCobros(v.id)}
            >
              <td className="p-2 font-mono">{v.recibo_num}</td>
              <td className="text-right p-2 font-mono">{v.importe}</td>
              <td className="text-right p-2 font-mono">{v.acumulado}</td>
              <td className="p-2">{v.estado}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {seleccionado && (
        <>
          <h2 className="font-semibold mb-2">Historial</h2>
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b">
                <th className="text-left p-2">Fecha</th>
                <th className="text-right p-2">Importe</th>
                <th className="text-left p-2">Cuenta</th>
              </tr>
            </thead>
            <tbody>
              {cobros.map((c) => (
                <tr key={c.id} className="border-b">
                  <td className="p-2 font-mono">{c.fecha}</td>
                  <td className="text-right p-2 font-mono">{c.importe}</td>
                  <td className="p-2 font-mono">{c.cuenta_tesoreria}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </main>
  );
}
