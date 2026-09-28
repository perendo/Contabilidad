"use client";

import { useEffect, useState } from "react";

import { ApiError } from "../../../components/treasury/api";
import { get } from "../../../services/client";

interface Periodo {
  id: string;
  numero_periodo: number;
  ejercicio: number;
  cuenta_id: number;
  fecha_inicio: string;
  fecha_fin: string;
  saldo_banco: string;
  saldo_libros: string;
}

export default function PeriodosPage() {
  const [periodos, setPeriodos] = useState<Periodo[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<{ items: Periodo[] }>("/api/v1/periodos-conciliados")
      .then((c) => setPeriodos(c.items))
      .catch((e) => {
        if (e instanceof ApiError) setError(e.message);
      });
  }, []);

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Períodos conciliados</h1>
      {error && <p className="text-red-600 mb-4">{error}</p>}
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b">
            <th className="text-right p-2">Nº</th>
            <th className="text-right p-2">Ejercicio</th>
            <th className="text-left p-2">Rango</th>
            <th className="text-right p-2">Saldo banco</th>
            <th className="text-right p-2">Saldo libros</th>
          </tr>
        </thead>
        <tbody>
          {periodos.map((p) => (
            <tr key={p.id} className="border-b">
              <td className="text-right p-2 font-mono">{p.numero_periodo}</td>
              <td className="text-right p-2">{p.ejercicio}</td>
              <td className="p-2 font-mono">{p.fecha_inicio} → {p.fecha_fin}</td>
              <td className="text-right p-2 font-mono">{p.saldo_banco}</td>
              <td className="text-right p-2 font-mono">{p.saldo_libros}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
