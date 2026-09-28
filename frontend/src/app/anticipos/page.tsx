"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AnticipoItem, listarAnticipos, TipoAnticipo } from "@/components/treasury/api";

export default function AnticiposPage() {
  const [items, setItems] = useState<AnticipoItem[]>([]);
  const [total, setTotal] = useState(0);
  const [tipo, setTipo] = useState<string>("");
  const [estado, setEstado] = useState<string>("");
  const [offset, setOffset] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    try {
      setCargando(true);
      setError(null);
      const res = await listarAnticipos({
        tipo: (tipo as TipoAnticipo) || undefined,
        estado: (estado as AnticipoItem["estado"]) || undefined,
        limit: 50,
        offset,
      });
      setItems(res.items);
      setTotal(res.total);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error al listar anticipos");
    } finally {
      setCargando(false);
    }
  }, [tipo, estado, offset]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Anticipos</h1>
          <p className="text-sm text-gray-500">
            Anticipos de clientes y proveedores, fondos a cuenta y su saldo
          </p>
        </div>
        <Link
          href="/anticipos/nuevo"
          className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
        >
          Nuevo Anticipo
        </Link>
      </div>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 p-4 text-red-700">
          {error}
        </div>
      )}

      <div className="flex gap-4 rounded border bg-white p-4">
        <div>
          <label className="block text-xs font-semibold text-gray-600">Tipo</label>
          <select
            className="mt-1 rounded border p-2 text-sm"
            value={tipo}
            onChange={(e) => {
              setTipo(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">Todos</option>
            <option value="CLIENTE">Cliente</option>
            <option value="PROVEEDOR">Proveedor</option>
          </select>
        </div>
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
            <option value="pendiente">pendiente</option>
            <option value="parcialmente_aplicado">parcialmente_aplicado</option>
            <option value="totalmente_aplicado">totalmente_aplicado</option>
          </select>
        </div>
      </div>

      <div className="overflow-hidden rounded border bg-white">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-3">Tercero</th>
              <th className="px-4 py-3">Tipo</th>
              <th className="px-4 py-3">Fecha</th>
              <th className="px-4 py-3 text-right">Importe</th>
              <th className="px-4 py-3 text-right">Saldo</th>
              <th className="px-4 py-3">Estado</th>
            </tr>
          </thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.id} className="border-t hover:bg-gray-50">
                <td className="px-4 py-3">
                  <Link href={`/anticipos/${i.id}`} className="font-medium text-blue-600 hover:underline">
                    {i.tercero_nombre || i.tercero_id.slice(0, 8)}
                  </Link>
                </td>
                <td className="px-4 py-3">{i.tipo}</td>
                <td className="px-4 py-3">{i.fecha}</td>
                <td className="px-4 py-3 text-right font-mono">{i.importe}</td>
                <td className="px-4 py-3 text-right font-mono font-semibold">
                  {i.saldo_pendiente}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`rounded px-2 py-1 text-xs font-semibold ${
                      i.estado === "totalmente_aplicado"
                        ? "bg-green-100 text-green-800"
                        : i.estado === "parcialmente_aplicado"
                        ? "bg-yellow-100 text-yellow-800"
                        : "bg-blue-100 text-blue-800"
                    }`}
                  >
                    {i.estado}
                  </span>
                </td>
              </tr>
            ))}
            {!cargando && items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                  No hay anticipos registrados.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-sm">
        <span className="text-gray-500">
          {total} anticipos — mostrando {offset + 1}–{offset + items.length}
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