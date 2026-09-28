"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../../components/treasury/api";
import { get } from "../../services/client";

interface Extracto {
  id: string;
  cuenta_id: number;
  fecha_inicio: string;
  fecha_fin: string;
  saldo_final: string;
  n_movimientos: number;
  estado: string;
}

interface Conciliacion {
  id: string;
  cuenta_id: number;
  estado: string;
  diferencia: string;
}

export default function ConciliacionPage() {
  const [extractos, setExtractos] = useState<Extracto[]>([]);
  const [conciliaciones, setConciliaciones] = useState<Conciliacion[]>([]);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setError(null);
    try {
      const [e, c] = await Promise.all([
        get<{ items: Extracto[] }>("/api/v1/extractos"),
        get<{ items: Conciliacion[] }>("/api/v1/conciliaciones"),
      ]);
      setExtractos(e.items);
      setConciliaciones(c.items);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <div className="flex items-baseline justify-between mb-4">
        <h1 className="text-xl font-semibold">Conciliación bancaria</h1>
        <Link href="/conciliacion/importar" className="bg-blue-600 text-white rounded px-3 py-1">
          Importar extracto
        </Link>
      </div>
      {error && <p className="text-red-600 mb-4">{error}</p>}
      <h2 className="font-semibold mb-2">Extractos</h2>
      <table className="w-full border-collapse text-sm mb-6">
        <thead>
          <tr className="border-b">
            <th className="text-left p-2">Rango</th>
            <th className="text-right p-2">Saldo final</th>
            <th className="text-right p-2">Nº mov.</th>
            <th className="text-left p-2">Estado</th>
          </tr>
        </thead>
        <tbody>
          {extractos.map((e) => (
            <tr key={e.id} className="border-b">
              <td className="p-2 font-mono">{e.fecha_inicio} → {e.fecha_fin}</td>
              <td className="text-right p-2 font-mono">{e.saldo_final}</td>
              <td className="text-right p-2">{e.n_movimientos}</td>
              <td className="p-2">{e.estado}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h2 className="font-semibold mb-2">Conciliaciones</h2>
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b">
            <th className="text-left p-2">Cuenta</th>
            <th className="text-left p-2">Estado</th>
            <th className="text-right p-2">Diferencia</th>
            <th className="p-2" />
          </tr>
        </thead>
        <tbody>
          {conciliaciones.map((c) => (
            <tr key={c.id} className="border-b">
              <td className="p-2 font-mono">{c.cuenta_id}</td>
              <td className="p-2">{c.estado}</td>
              <td className="text-right p-2 font-mono">{c.diferencia}</td>
              <td className="p-2 text-right">
                <Link href={`/conciliacion/${c.id}`} className="text-blue-700 underline">
                  Abrir
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
