"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  formatearImporte,
  listarCalculos,
  type CalculoResumen,
  type EstadoCalculo,
} from "@/components/fiscal/api";

const TAMANO_PAGINA = 50;
const ESTADOS: EstadoCalculo[] = ["borrador", "calculado", "contabilizado"];

type FiltroProvisional = "" | "true" | "false";

export default function ImpuestoSociedadesPage() {
  const [items, setItems] = useState<CalculoResumen[]>([]);
  const [total, setTotal] = useState(0);
  const [ejercicio, setEjercicio] = useState(new Date().getFullYear());
  const [provisional, setProvisional] = useState<FiltroProvisional>("");
  const [estado, setEstado] = useState<EstadoCalculo | "">("");
  const [offset, setOffset] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const respuesta = await listarCalculos({
        ejercicio: ejercicio || undefined,
        provisional: provisional === "" ? undefined : provisional === "true",
        estado: estado || undefined,
        limit: TAMANO_PAGINA,
        offset,
      });
      setItems(respuesta.items);
      setTotal(respuesta.total);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error al listar los cálculos");
    } finally {
      setCargando(false);
    }
  }, [ejercicio, estado, offset, provisional]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  return (
    <main className="mx-auto max-w-6xl space-y-6 p-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Impuesto sobre Sociedades</h1>
          <p className="text-sm text-gray-500">
            Cálculo, ajustes extracontables y contabilización del IS
          </p>
        </div>
        <Link
          href="/fiscal/impuesto-sociedades/nuevo"
          className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
        >
          Nuevo cálculo
        </Link>
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
          <span className="font-semibold text-gray-600">Modalidad</span>
          <select
            value={provisional}
            onChange={(e) => {
              setProvisional(e.target.value as FiltroProvisional);
              setOffset(0);
            }}
            className="mt-1 block rounded border p-2"
          >
            <option value="">Todas</option>
            <option value="true">Provisional</option>
            <option value="false">Definitivo</option>
          </select>
        </label>
        <label className="block text-sm">
          <span className="font-semibold text-gray-600">Estado</span>
          <select
            value={estado}
            onChange={(e) => {
              setEstado(e.target.value as EstadoCalculo | "");
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

      <div className="overflow-hidden rounded border bg-white">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-3">Ejercicio</th>
              <th className="px-4 py-3">Base imponible</th>
              <th className="px-4 py-3">Cuota íntegra</th>
              <th className="px-4 py-3">Cuota diferencial</th>
              <th className="px-4 py-3">Modalidad</th>
              <th className="px-4 py-3">Estado</th>
            </tr>
          </thead>
          <tbody>
            {items.map((calculo) => (
              <tr key={calculo.id} className="border-t hover:bg-gray-50">
                <td className="px-4 py-3">
                  <Link
                    href={`/fiscal/impuesto-sociedades/${calculo.id}`}
                    className="font-semibold text-blue-600 hover:underline"
                  >
                    {calculo.ejercicio}
                  </Link>
                </td>
                <td className="px-4 py-3 font-mono">
                  {formatearImporte(calculo.base_imponible)}
                </td>
                <td className="px-4 py-3 font-mono">
                  {formatearImporte(calculo.cuota_integra)}
                </td>
                <td className="px-4 py-3 font-mono">
                  {formatearImporte(calculo.cuota_diferencial)}
                </td>
                <td className="px-4 py-3">
                  {calculo.provisional ? "Provisional" : "Definitivo"}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`rounded px-2 py-1 text-xs font-semibold ${
                      calculo.estado === "contabilizado"
                        ? "bg-green-100 text-green-800"
                        : calculo.estado === "calculado"
                          ? "bg-blue-100 text-blue-800"
                          : "bg-gray-100 text-gray-800"
                    }`}
                  >
                    {calculo.estado}
                  </span>
                </td>
              </tr>
            ))}
            {!cargando && items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                  No hay cálculos para estos filtros.
                </td>
              </tr>
            )}
            {cargando && items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-500">
                  Cargando cálculos…
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
