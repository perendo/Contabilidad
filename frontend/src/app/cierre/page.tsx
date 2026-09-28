"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../../components/treasury/api";
import { get, post } from "../../services/client";

interface Ejercicio {
  year: number;
  date_start: string;
  date_end: string;
  is_closed: boolean;
  closed_at: string | null;
}

export default function CierrePage() {
  const [ejercicios, setEjercicios] = useState<Ejercicio[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [cerrando, setCerrando] = useState<number | null>(null);

  const cargar = useCallback(async () => {
    try {
      const cuerpo = await get<{ items: Ejercicio[] }>("/api/v1/fiscal-years");
      setEjercicios(cuerpo.items);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  async function cerrar(year: number) {
    if (!window.confirm(`¿Cerrar el ejercicio ${year}? No se podrá reabrir.`)) return;
    setError(null);
    setCerrando(year);
    try {
      await post(`/api/v1/fiscal-years/${year}/close`);
      await cargar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    } finally {
      setCerrando(null);
    }
  }

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Cierre de ejercicio</h1>
      {error && <p className="text-red-600 mb-4">{error}</p>}
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b">
            <th className="text-left p-2">Ejercicio</th>
            <th className="text-left p-2">Rango</th>
            <th className="text-left p-2">Estado</th>
            <th className="p-2" />
          </tr>
        </thead>
        <tbody>
          {ejercicios.map((e) => (
            <tr key={e.year} className="border-b">
              <td className="p-2 font-mono">{e.year}</td>
              <td className="p-2 font-mono">
                {e.date_start} → {e.date_end}
              </td>
              <td className="p-2">{e.is_closed ? "Cerrado" : "Abierto"}</td>
              <td className="p-2 text-right">
                {!e.is_closed && (
                  <button
                    onClick={() => cerrar(e.year)}
                    disabled={cerrando === e.year}
                    className="bg-blue-600 text-white rounded px-3 py-1 disabled:opacity-50"
                  >
                    {cerrando === e.year ? "Cerrando…" : "Cerrar"}
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
