"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import {
  ApiError,
  descargarModelo200,
  generarModelo200,
  listarModelos200,
  type Modelo200,
} from "@/components/fiscal/api";

export default function Modelo200Page() {
  const [items, setItems] = useState<Modelo200[]>([]);
  const [total, setTotal] = useState(0);
  const [calculoId, setCalculoId] = useState("");
  const [cargando, setCargando] = useState(true);
  const [generando, setGenerando] = useState(false);
  const [descargandoId, setDescargandoId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mensaje, setMensaje] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const respuesta = await listarModelos200({ limit: 50, offset: 0 });
      setItems(respuesta.items);
      setTotal(respuesta.total);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error al listar los modelos 200");
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  async function generar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    setGenerando(true);
    setError(null);
    setMensaje(null);
    try {
      const modelo = await generarModelo200({ calculo_is_id: calculoId.trim() });
      setCalculoId("");
      await cargar();
      setMensaje(`Modelo 200 generado con identificador ${modelo.id}.`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error al generar el modelo 200");
    } finally {
      setGenerando(false);
    }
  }

  async function descargar(modelo: Modelo200) {
    setDescargandoId(modelo.id);
    setError(null);
    setMensaje(null);
    try {
      await descargarModelo200(
        modelo.id,
        modelo.nombre_fichero ?? `modelo-200-${modelo.id}.csv`
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error al descargar el modelo 200");
    } finally {
      setDescargandoId(null);
    }
  }

  return (
    <main className="mx-auto max-w-6xl space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Modelo 200</h1>
          <p className="text-sm text-gray-500">
            Soportes generados a partir de cálculos de Impuesto sobre Sociedades
            contabilizados
          </p>
        </div>
        <Link
          href="/fiscal/impuesto-sociedades"
          className="rounded border px-4 py-2 text-sm font-semibold text-blue-700 hover:bg-blue-50"
        >
          Ver cálculos
        </Link>
      </div>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 p-4 text-red-700">
          {error}
        </div>
      )}
      {mensaje && (
        <div className="rounded border border-green-200 bg-green-50 p-4 text-green-700">
          {mensaje}
        </div>
      )}

      <form onSubmit={generar} className="rounded border bg-gray-50 p-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="block flex-1 text-sm font-semibold text-gray-600">
            Cálculo contabilizado (UUID)
            <input
              type="text"
              required
              value={calculoId}
              onChange={(e) => setCalculoId(e.target.value)}
              placeholder="Identificador del cálculo"
              className="mt-1 block w-full rounded border bg-white p-2 font-mono text-sm"
            />
          </label>
          <button
            type="submit"
            disabled={generando}
            className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {generando ? "Generando…" : "Generar modelo 200"}
          </button>
        </div>
      </form>

      <div className="overflow-hidden rounded border bg-white">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-3">Modelo</th>
              <th className="px-4 py-3">Cálculo</th>
              <th className="px-4 py-3">Generado</th>
              <th className="px-4 py-3">SHA-256</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {items.map((modelo) => (
              <tr key={modelo.id} className="border-t hover:bg-gray-50">
                <td className="px-4 py-3 font-mono text-xs">{modelo.id}</td>
                <td className="px-4 py-3 font-mono text-xs">{modelo.calculo_is_id}</td>
                <td className="px-4 py-3">{modelo.fecha_generacion}</td>
                <td className="px-4 py-3 font-mono text-xs">{modelo.hash_contenido}</td>
                <td className="px-4 py-3 text-right">
                  <button
                    type="button"
                    onClick={() => void descargar(modelo)}
                    disabled={descargandoId !== null}
                    className="text-blue-700 underline disabled:opacity-40"
                  >
                    {descargandoId === modelo.id ? "Descargando…" : "Descargar"}
                  </button>
                </td>
              </tr>
            ))}
            {!cargando && items.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                  No hay modelos 200 generados.
                </td>
              </tr>
            )}
            {cargando && items.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gray-500">
                  Cargando modelos…
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <p className="text-sm text-gray-500">{total} modelos generados</p>
    </main>
  );
}
