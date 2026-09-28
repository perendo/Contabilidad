"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import {
  ApiError,
  descargarLegalizacion,
  descargarLibro,
  emitirLegalizacion,
  generarLibros,
  listarLegalizaciones,
  listarLibros,
  type Legalizacion,
  type Libro,
  type TipoLibro,
} from "../../../components/ngo/api";

const TIPOS_LIBRO: TipoLibro[] = ["diario", "mayor", "balance", "pyg"];

export default function LibrosPage() {
  const [ejercicio, setEjercicio] = useState(new Date().getFullYear());
  const [tipos, setTipos] = useState<TipoLibro[]>(["diario", "mayor"]);
  const [libros, setLibros] = useState<Libro[]>([]);
  const [legalizaciones, setLegalizaciones] = useState<Legalizacion[]>([]);
  const [fechaLegalizacion, setFechaLegalizacion] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [mensaje, setMensaje] = useState<string | null>(null);

  const consultar = useCallback(async () => {
    setError(null);
    try {
      const [lb, lg] = await Promise.all([listarLibros(ejercicio), listarLegalizaciones()]);
      setLibros(lb.items);
      setLegalizaciones(lg.items);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    }
  }, [ejercicio]);

  useEffect(() => {
    consultar();
  }, [consultar]);

  async function alGenerar(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setMensaje(null);
    try {
      const generados = await generarLibros(ejercicio, tipos);
      setMensaje(
        generados
          .map((g) => `${g.tipo} ${g.reusado ? "(reutilizado)" : "OK"}`)
          .join(" · ")
      );
      consultar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }

  async function alLegalizar(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setMensaje(null);
    try {
      const lg = await emitirLegalizacion(ejercicio, fechaLegalizacion || null);
      setMensaje(`Legalización emitida (${lg.total_asientos} asientos)`);
      consultar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }

  function alternarTipo(tipo: TipoLibro) {
    setTipos((prev) =>
      prev.includes(tipo) ? prev.filter((t) => t !== tipo) : [...prev, tipo]
    );
  }

  return (
    <main className="p-6 max-w-4xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Libros oficiales y legalización</h1>

      {mensaje && <p className="text-green-700 mb-4">{mensaje}</p>}
      {error && <p className="text-red-600 mb-4">{error}</p>}

      <form onSubmit={alGenerar} className="border rounded p-4 mb-6 bg-gray-50">
        <div className="flex items-center gap-3 mb-3">
          <label className="text-sm text-gray-600">Ejercicio</label>
          <input
            value={ejercicio}
            onChange={(e) => setEjercicio(Number(e.target.value))}
            type="number"
            className="border rounded px-3 py-2 w-24"
          />
          <div className="flex items-center gap-3">
            {TIPOS_LIBRO.map((t) => (
              <label key={t} className="flex items-center gap-1 text-sm">
                <input
                  type="checkbox"
                  checked={tipos.includes(t)}
                  onChange={() => alternarTipo(t)}
                />
                {t}
              </label>
            ))}
          </div>
        </div>
        <button
          type="submit"
          className="bg-blue-600 text-white rounded px-4 py-2"
        >
          Generar libros
        </button>
      </form>

      <h2 className="text-lg font-semibold mb-2">Libros del ejercicio {ejercicio}</h2>
      <table className="w-full text-sm border rounded mb-6">
        <thead>
          <tr className="text-left bg-gray-100">
            <th className="p-2">Tipo</th>
            <th className="p-2">SHA-256</th>
            <th className="p-2">Tamaño</th>
            <th className="p-2"></th>
          </tr>
        </thead>
        <tbody>
          {libros.map((l) => (
            <tr key={l.id} className="border-t">
              <td className="p-2">{l.tipo}</td>
              <td className="p-2 font-mono text-xs">{l.sha256}</td>
              <td className="p-2 font-mono">{l.size_bytes} bytes</td>
              <td className="p-2">
                <button
                  onClick={() => descargarLibro(l.id)}
                  className="text-blue-600 underline text-sm"
                >
                  Descargar PDF
                </button>
              </td>
            </tr>
          ))}
          {libros.length === 0 && (
            <tr>
              <td colSpan={4} className="p-2 text-gray-500">
                Aún no hay libros generados para este ejercicio
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <h2 className="text-lg font-semibold mb-2">Legalización del diario</h2>
      <form onSubmit={alLegalizar} className="border rounded p-4 mb-4 bg-gray-50 flex items-end gap-3">
        <div>
          <label className="text-sm text-gray-600 block">Ejercicio</label>
          <input
            value={ejercicio}
            onChange={(e) => setEjercicio(Number(e.target.value))}
            type="number"
            className="border rounded px-3 py-2"
          />
        </div>
        <div>
          <label className="text-sm text-gray-600 block">
            Fecha de legalización (opcional)
          </label>
          <input
            value={fechaLegalizacion}
            onChange={(e) => setFechaLegalizacion(e.target.value)}
            type="date"
            className="border rounded px-3 py-2"
          />
        </div>
        <button
          type="submit"
          className="bg-green-600 text-white rounded px-4 py-2"
        >
          Emitir legalización
        </button>
      </form>

      <table className="w-full text-sm border rounded">
        <thead>
          <tr className="text-left bg-gray-100">
            <th className="p-2">Ejercicio</th>
            <th className="p-2">Rango</th>
            <th className="p-2">Asientos</th>
            <th className="p-2">Emisión</th>
            <th className="p-2">Huella</th>
            <th className="p-2"></th>
          </tr>
        </thead>
        <tbody>
          {legalizaciones.map((l) => (
            <tr key={l.id} className="border-t">
              <td className="p-2">{l.ejercicio}</td>
              <td className="p-2 font-mono">
                {l.rango_asientos_desde}–{l.rango_asientos_hasta}
              </td>
              <td className="p-2">{l.total_asientos}</td>
              <td className="p-2 text-xs">{l.fecha_emision}</td>
              <td className="p-2 font-mono text-xs">{l.huella}</td>
              <td className="p-2">
                <button
                  onClick={() => descargarLegalizacion(l.id)}
                  className="text-blue-600 underline text-sm"
                >
                  Descargar .txt
                </button>
              </td>
            </tr>
          ))}
          {legalizaciones.length === 0 && (
            <tr>
              <td colSpan={6} className="p-2 text-gray-500">
                Ningún ejercicio legalizado
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </main>
  );
}