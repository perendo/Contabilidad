"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  EfectoItem,
  EstadoEfecto,
  listarEfectos,
  ResumenCartera,
  TipoEfecto,
} from "@/components/treasury/api";

export default function EfectosPage() {
  const [datos, setDatos] = useState<ResumenCartera | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [estado, setEstado] = useState<EstadoEfecto | "">("");
  const [tipo, setTipo] = useState<TipoEfecto | "">("");
  const [fechaDesde, setFechaDesde] = useState("");
  const [fechaHasta, setFechaHasta] = useState("");

  const cargar = useCallback(async () => {
    try {
      setCargando(true);
      setError(null);
      const res = await listarEfectos({
        estado: (estado || undefined) as EstadoEfecto | undefined,
        tipo_efecto: (tipo || undefined) as TipoEfecto | undefined,
        fecha_desde: fechaDesde || undefined,
        fecha_hasta: fechaHasta || undefined,
      });
      setDatos(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error al cargar efectos");
    } finally {
      setCargando(false);
    }
  }, [estado, tipo, fechaDesde, fechaHasta]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Cartera de Efectos</h1>
          <p className="text-sm text-gray-500">
            Cheques, pagarés y letras de cambio
          </p>
        </div>
        <Link
          href="/efectos/nuevo"
          className="rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
        >
          Nuevo Efecto
        </Link>
      </div>

      <div className="grid grid-cols-1 gap-4 rounded border bg-gray-50 p-4 md:grid-cols-4">
        <div>
          <label className="block text-xs font-semibold text-gray-600">Estado</label>
          <select
            className="mt-1 w-full rounded border bg-white p-2 text-sm"
            value={estado}
            onChange={(e) => setEstado(e.target.value as EstadoEfecto | "")}
          >
            <option value="">Todos los estados</option>
            <option value="emitido">Emitido</option>
            <option value="cobrado">Cobrado</option>
            <option value="impagado">Impagado</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-semibold text-gray-600">Tipo</label>
          <select
            className="mt-1 w-full rounded border bg-white p-2 text-sm"
            value={tipo}
            onChange={(e) => setTipo(e.target.value as TipoEfecto | "")}
          >
            <option value="">Todos los tipos</option>
            <option value="CHEQUE">Cheque</option>
            <option value="PAGARE">Pagaré</option>
            <option value="LETRA">Letra de cambio</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-semibold text-gray-600">Vence desde</label>
          <input
            type="date"
            className="mt-1 w-full rounded border bg-white p-2 text-sm"
            value={fechaDesde}
            onChange={(e) => setFechaDesde(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-gray-600">Vence hasta</label>
          <input
            type="date"
            className="mt-1 w-full rounded border bg-white p-2 text-sm"
            value={fechaHasta}
            onChange={(e) => setFechaHasta(e.target.value)}
          />
        </div>
      </div>

      {datos && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
          {datos.por_estado.map((item) => (
            <div key={item.estado} className="rounded border bg-white p-4">
              <div className="text-xs uppercase text-gray-500">{item.estado}</div>
              <div className="text-xl font-bold">{item.importe} €</div>
              <div className="text-xs text-gray-400">{item.total} efectos</div>
            </div>
          ))}
        </div>
      )}

      {error && (
        <div className="rounded border border-red-200 bg-red-50 p-4 text-red-700">
          {error}
        </div>
      )}

      {cargando ? (
        <div className="p-8 text-center text-gray-500">Cargando efectos...</div>
      ) : (
        <div className="overflow-x-auto rounded border bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b bg-gray-100 text-xs uppercase text-gray-600">
              <tr>
                <th className="p-3">Documento</th>
                <th className="p-3">Tipo</th>
                <th className="p-3">Tercero</th>
                <th className="p-3">Emisión</th>
                <th className="p-3">Vencimiento</th>
                <th className="p-3 text-right">Importe</th>
                <th className="p-3">Estado</th>
                <th className="p-3"></th>
              </tr>
            </thead>
            <tbody>
              {!datos || datos.items.length === 0 ? (
                <tr>
                  <td colSpan={8} className="p-6 text-center text-gray-400">
                    No hay efectos registrados
                  </td>
                </tr>
              ) : (
                datos.items.map((item: EfectoItem) => (
                  <tr key={item.id} className="border-b hover:bg-gray-50">
                    <td className="p-3 font-mono font-medium">{item.numero_documento}</td>
                    <td className="p-3">{item.tipo_efecto}</td>
                    <td className="p-3">{item.tercero_nombre || item.tercero_id.slice(0, 8)}</td>
                    <td className="p-3 text-gray-600">{item.fecha_emision}</td>
                    <td className="p-3 text-gray-600">{item.fecha_vencimiento}</td>
                    <td className="p-3 text-right font-mono font-semibold">
                      {item.importe} €
                    </td>
                    <td className="p-3">
                      <span
                        className={`rounded px-2 py-0.5 text-xs font-semibold ${
                          item.estado === "cobrado"
                            ? "bg-green-100 text-green-800"
                            : item.estado === "impagado"
                            ? "bg-red-100 text-red-800"
                            : "bg-yellow-100 text-yellow-800"
                        }`}
                      >
                        {item.estado}
                      </span>
                    </td>
                    <td className="p-3 text-right">
                      <Link
                        href={`/efectos/${item.id}`}
                        className="text-blue-600 hover:underline"
                      >
                        Detalle
                      </Link>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
