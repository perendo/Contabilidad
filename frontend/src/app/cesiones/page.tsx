"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { CesionItem, EstadoCesion, listarCesiones } from "@/components/treasury/api";

export default function CesionesPage() {
  const [items, setItems] = useState<CesionItem[]>([]);
  const [total, setTotal] = useState(0);
  const [estado, setEstado] = useState<string>("");
  const [offset, setOffset] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    try {
      setCargando(true);
      setError(null);
      const res = await listarCesiones({
        estado: (estado as EstadoCesion) || undefined,
        limit: 50,
        offset,
      });
      setItems(res.items);
      setTotal(res.total);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error al listar cesiones");
    } finally {
      setCargando(false);
    }
  }, [estado, offset]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Cesión de Cobros</h1>
          <p className="text-sm text-gray-500">
            Cesión a entidades financieras con comisión y notificación al deudor
          </p>
        </div>
        <Link
          href="/cesiones/nueva"
          className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
        >
          Nueva Cesión
        </Link>
      </div>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 p-4 text-red-700">
          {error}
        </div>
      )}

      <div className="flex gap-4 rounded border bg-white p-4">
        <div>
          <label className="block text-xs font-semibold text-gray-600">Estado</label>
          <select
            className="mt-1 rounded border p-2 text-sm"
            value={estado}
            onChange={(e) => {
              setEstado(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">Todos</option>
            <option value="activa">activa</option>
            <option value="saldada">saldada</option>
            <option value="cancelada">cancelada</option>
          </select>
        </div>
      </div>

      <div className="overflow-hidden rounded border bg-white">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-3">Entidad</th>
              <th className="px-4 py-3">Fecha</th>
              <th className="px-4 py-3 text-right">Total cedido</th>
              <th className="px-4 py-3 text-right">Comisión</th>
              <th className="px-4 py-3 text-right">Vencimientos</th>
              <th className="px-4 py-3">Estado</th>
            </tr>
          </thead>
          <tbody>
            {items.map((c) => (
              <tr key={c.id} className="border-t hover:bg-gray-50">
                <td className="px-4 py-3">
                  <Link href={`/cesiones/${c.id}`} className="font-medium text-blue-600 hover:underline">
                    {c.entidad_financiera}
                  </Link>
                </td>
                <td className="px-4 py-3">{c.fecha_cesion}</td>
                <td className="px-4 py-3 text-right font-mono">{c.importe_total_cedido}</td>
                <td className="px-4 py-3 text-right font-mono">{c.comision}</td>
                <td className="px-4 py-3 text-right">{c.n_vencimientos}</td>
                <td className="px-4 py-3">
                  <span
                    className={`rounded px-2 py-1 text-xs font-semibold ${
                      c.estado === "saldada"
                        ? "bg-green-100 text-green-800"
                        : c.estado === "cancelada"
                        ? "bg-red-100 text-red-800"
                        : "bg-blue-100 text-blue-800"
                    }`}
                  >
                    {c.estado}
                  </span>
                </td>
              </tr>
            ))}
            {!cargando && items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                  No hay cesiones registradas.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-sm">
        <span className="text-gray-500">
          {total} cesiones — mostrando {offset + 1}–{offset + items.length}
        </span>
        <div className="space-x-2">
          <button
            type="button"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - 50))}
            className="rounded border px-3 py-1.5 disabled:opacity-40"
          >
            Anterior
          </button>
          <button
            type="button"
            disabled={offset + items.length >= total}
            onClick={() => setOffset(offset + 50)}
            className="rounded border px-3 py-1.5 disabled:opacity-40"
          >
            Siguiente
          </button>
        </div>
      </div>
    </div>
  );
}