"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  cambiarEstadoSerie,
  crearSerie,
  listarSeries,
  type SerieFactura,
} from "../../../components/invoicing/api";
import { ApiError } from "../../../components/treasury/api";

export default function SeriesPage() {
  const [series, setSeries] = useState<SerieFactura[]>([]);
  const [codigo, setCodigo] = useState("");
  const [nombre, setNombre] = useState("");
  const [prefijo, setPrefijo] = useState("");
  const [sufijo, setSufijo] = useState("");
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setError(null);
    try {
      setSeries(await listarSeries());
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  async function crear() {
    setError(null);
    try {
      await crearSerie({
        codigo,
        nombre: nombre || undefined,
        prefijo: prefijo || undefined,
        sufijo,
      });
      setCodigo("");
      setNombre("");
      setPrefijo("");
      setSufijo("");
      await cargar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }

  async function alternar(serie: SerieFactura) {
    setError(null);
    try {
      await cambiarEstadoSerie(serie.id, serie.estado !== "activa");
      await cargar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }

  return (
    <main className="p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">Series de facturación</h1>
        <Link href="/facturacion/facturas" className="text-blue-700 underline">
          Facturas
        </Link>
      </div>

      {error && <p className="text-red-600 mb-4">{error}</p>}

      <div className="flex flex-wrap items-end gap-3 mb-6">
        <label className="block">
          <span className="text-sm">Código</span>
          <input
            value={codigo}
            onChange={(e) => setCodigo(e.target.value)}
            className="border rounded px-2 py-1 mt-1 w-24"
          />
        </label>
        <label className="block">
          <span className="text-sm">Nombre</span>
          <input
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            className="border rounded px-2 py-1 mt-1 w-40"
          />
        </label>
        <label className="block">
          <span className="text-sm">Prefijo</span>
          <input
            value={prefijo}
            onChange={(e) => setPrefijo(e.target.value)}
            className="border rounded px-2 py-1 mt-1 w-24"
          />
        </label>
        <label className="block">
          <span className="text-sm">Sufijo</span>
          <input
            value={sufijo}
            onChange={(e) => setSufijo(e.target.value)}
            className="border rounded px-2 py-1 mt-1 w-24"
          />
        </label>
        <button
          onClick={crear}
          disabled={!codigo}
          className="bg-blue-600 text-white rounded px-4 py-2 disabled:opacity-50"
        >
          Crear serie
        </button>
      </div>

      <table className="w-full text-sm border">
        <thead className="bg-gray-100">
          <tr>
            <th className="text-left p-2">Código</th>
            <th className="text-left p-2">Nombre</th>
            <th className="text-left p-2">Ejemplo</th>
            <th className="text-right p-2">Siguiente</th>
            <th className="text-left p-2">Estado</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {series.map((s) => (
            <tr key={s.id} className="border-t">
              <td className="p-2">{s.codigo}</td>
              <td className="p-2">{s.nombre}</td>
              <td className="p-2 font-mono">{s.correlativo_ejemplo}</td>
              <td className="p-2 text-right">{s.siguiente_numero}</td>
              <td className="p-2">{s.estado}</td>
              <td className="p-2 text-right">
                <button
                  onClick={() => alternar(s)}
                  className="text-blue-700 underline"
                >
                  {s.estado === "activa" ? "Desactivar" : "Activar"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
