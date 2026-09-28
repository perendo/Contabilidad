"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  formatearImporte,
  listarLiquidaciones,
  type EstadoLiquidacion,
  type LiquidacionResumen,
} from "@/components/fiscal/api";
import { suscribirEmpresa } from "@/components/treasury/empresa";

const TAMANO_PAGINA = 50;
const TRIMESTRES = [1, 2, 3, 4];
const ESTADOS: EstadoLiquidacion[] = ["pendiente", "liquidado"];

export default function RetencionesPage() {
  const [items, setItems] = useState<LiquidacionResumen[]>([]);
  const [total, setTotal] = useState(0);
  const [ejercicio, setEjercicio] = useState(new Date().getFullYear());
  const [trimestre, setTrimestre] = useState<number | "">("");
  const [estado, setEstado] = useState<EstadoLiquidacion | "">("");
  const [offset, setOffset] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revisionEmpresa, setRevisionEmpresa] = useState(0);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const respuesta = await listarLiquidaciones({
        ejercicio: ejercicio || undefined,
        trimestre: trimestre === "" ? undefined : trimestre,
        estado: estado || undefined,
        limit: TAMANO_PAGINA,
        offset,
      });
      setItems(respuesta.items);
      setTotal(respuesta.total);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error al listar las liquidaciones");
    } finally {
      setCargando(false);
    }
  }, [ejercicio, estado, offset, trimestre]);

  useEffect(() => {
    void cargar();
  }, [cargar, revisionEmpresa]);

  useEffect(() => {
    return suscribirEmpresa(() => {
      setOffset(0);
      setRevisionEmpresa((revision) => revision + 1);
    });
  }, []);

  return (
    <main className="mx-auto max-w-6xl space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Retenciones IRPF</h1>
          <p className="text-sm text-gray-500">
            Liquidaciones trimestrales, retenciones por perceptor y modelos 111/115
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            href="/fiscal/modelos/190"
            className="rounded border px-4 py-2 text-sm font-semibold text-blue-700 hover:bg-blue-50"
          >
            Modelo 190
          </Link>
          <Link
            href="/fiscal/retenciones/nueva"
            className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
          >
            Nueva liquidación
          </Link>
        </div>
      </div>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 p-4 text-red-700">
          {error}
        </div>
      )}

      <div className="flex flex-wrap items-end gap-4 rounded border bg-white p-4">
        <label className="block text-sm">
          <span className="font-semibold text-gray-600">Ejercicio</span>
          <input
            type="number"
            value={ejercicio}
            onChange={(e) => {
              setEjercicio(e.currentTarget.valueAsNumber);
              setOffset(0);
            }}
            className="mt-1 block w-28 rounded border p-2"
          />
        </label>
        <label className="block text-sm">
          <span className="font-semibold text-gray-600">Trimestre</span>
          <select
            value={trimestre}
            onChange={(e) => {
              setTrimestre(e.target.value === "" ? "" : Number(e.target.value));
              setOffset(0);
            }}
            className="mt-1 block rounded border p-2"
          >
            <option value="">Todos</option>
            {TRIMESTRES.map((valor) => (
              <option key={valor} value={valor}>
                Q{valor}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm">
          <span className="font-semibold text-gray-600">Estado</span>
          <select
            value={estado}
            onChange={(e) => {
              setEstado(e.target.value as EstadoLiquidacion | "");
              setOffset(0);
            }}
            className="mt-1 block rounded border p-2"
          >
            <option value="">Todos</option>
            {ESTADOS.map((valor) => (
              <option key={valor} value={valor}>
                {valor}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="overflow-x-auto rounded border bg-white">
        <table className="w-full min-w-[850px] text-sm">
          <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-3">Periodo</th>
              <th className="px-4 py-3">Base de retenciones</th>
              <th className="px-4 py-3">Retenciones</th>
              <th className="px-4 py-3">Perceptores</th>
              <th className="px-4 py-3">Estado</th>
              <th className="px-4 py-3">Fecha liquidación</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {items.map((liquidacion) => (
              <tr key={liquidacion.id} className="border-t hover:bg-gray-50">
                <td className="px-4 py-3">
                  <Link
                    href={`/fiscal/retenciones/${liquidacion.id}`}
                    className="font-semibold text-blue-600 hover:underline"
                  >
                    {liquidacion.periodo || `${liquidacion.ejercicio}-Q${liquidacion.trimestre}`}
                  </Link>
                </td>
                <td className="px-4 py-3 font-mono">
                  {liquidacion.total_base_retenciones
                    ? formatearImporte(liquidacion.total_base_retenciones)
                    : "—"}
                </td>
                <td className="px-4 py-3 font-mono font-semibold">
                  {formatearImporte(liquidacion.total_retenciones)}
                </td>
                <td className="px-4 py-3">{liquidacion.n_perceptores ?? "—"}</td>
                <td className="px-4 py-3">
                  <span
                    className={`rounded px-2 py-1 text-xs font-semibold ${
                      liquidacion.estado === "liquidado"
                        ? "bg-green-100 text-green-800"
                        : "bg-blue-100 text-blue-800"
                    }`}
                  >
                    {liquidacion.estado}
                  </span>
                </td>
                <td className="px-4 py-3">{liquidacion.fecha_liquidacion || "—"}</td>
                <td className="px-4 py-3 text-right">
                  <Link
                    href={`/fiscal/retenciones/${liquidacion.id}`}
                    className="text-blue-700 underline"
                  >
                    Abrir
                  </Link>
                </td>
              </tr>
            ))}
            {!cargando && items.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-400">
                  No hay liquidaciones para estos filtros.
                </td>
              </tr>
            )}
            {cargando && items.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-500">
                  Cargando liquidaciones…
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-sm text-gray-500">
        <span>
          {total === 0 ? 0 : offset + 1}–{offset + items.length} de {total}
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={offset === 0 || cargando}
            onClick={() => setOffset(Math.max(0, offset - TAMANO_PAGINA))}
            className="rounded border px-3 py-1.5 disabled:opacity-40"
          >
            Anterior
          </button>
          <button
            type="button"
            disabled={cargando || offset + items.length >= total}
            onClick={() => setOffset(offset + TAMANO_PAGINA)}
            className="rounded border px-3 py-1.5 disabled:opacity-40"
          >
            Siguiente
          </button>
        </div>
      </div>
    </main>
  );
}
