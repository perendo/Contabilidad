"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  liquidarAnticipo,
  obtenerAnticipo,
  DetalleAnticipo,
} from "@/components/treasury/api";

export default function DetalleAnticipoPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [anticipo, setAnticipo] = useState<DetalleAnticipo | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [facturaId, setFacturaId] = useState("");
  const [importeAplicado, setImporteAplicado] = useState("");
  const [fechaAplicacion, setFechaAplicacion] = useState(
    new Date().toISOString().slice(0, 10)
  );
  const [procesando, setProcesando] = useState(false);

  const cargar = useCallback(async () => {
    try {
      setCargando(true);
      setError(null);
      setAnticipo(await obtenerAnticipo(id));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error al cargar anticipo");
    } finally {
      setCargando(false);
    }
  }, [id]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const onLiquidar = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setProcesando(true);
      setError(null);
      await liquidarAnticipo(id, {
        aplicaciones: [
          { factura_id: facturaId.trim(), importe_aplicado: importeAplicado.trim() },
        ],
        fecha_aplicacion: fechaAplicacion,
      });
      setFacturaId("");
      setImporteAplicado("");
      await cargar();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error al liquidar anticipo");
    } finally {
      setProcesando(false);
    }
  };

  if (cargando) {
    return <div className="p-8 text-center text-gray-500">Cargando anticipo...</div>;
  }

  if (!anticipo) {
    return (
      <div className="space-y-4">
        <div className="text-red-600">{error || "Anticipo no encontrado"}</div>
        <button onClick={() => router.push("/anticipos")} className="text-blue-600 underline">
          Volver al listado
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs text-gray-500">
            <Link href="/anticipos" className="hover:underline">
              Anticipos
            </Link>{" "}
            / {anticipo.tipo}
          </div>
          <h1 className="text-2xl font-bold">
            {anticipo.tercero_nombre || anticipo.tercero_id.slice(0, 8)}
          </h1>
        </div>
        <span
          className={`rounded px-3 py-1 text-sm font-semibold ${
            anticipo.estado === "totalmente_aplicado"
              ? "bg-green-100 text-green-800"
              : anticipo.estado === "parcialmente_aplicado"
              ? "bg-yellow-100 text-yellow-800"
              : "bg-blue-100 text-blue-800"
          }`}
        >
          {anticipo.estado.toUpperCase()}
        </span>
      </div>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 p-4 text-red-700">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <div className="space-y-4 rounded border bg-white p-6">
          <h2 className="text-lg font-semibold">Datos del Anticipo</h2>
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <dt className="text-gray-500">Importe:</dt>
            <dd className="font-mono font-bold text-blue-600">{anticipo.importe}</dd>
            <dt className="text-gray-500">Saldo pendiente:</dt>
            <dd className="font-mono font-bold text-blue-600">
              {anticipo.saldo_pendiente}
            </dd>
            <dt className="text-gray-500">Tipo:</dt>
            <dd>{anticipo.tipo}</dd>
            <dt className="text-gray-500">Cuenta contable:</dt>
            <dd className="font-mono">{anticipo.cuenta_contable}</dd>
            <dt className="text-gray-500">Fecha:</dt>
            <dd>{anticipo.fecha}</dd>
            <dt className="text-gray-500">Asiento:</dt>
            <dd className="font-mono text-xs truncate">
              {anticipo.asiento_id || "—"}
            </dd>
            {anticipo.notas && (
              <>
                <dt className="text-gray-500">Notas:</dt>
                <dd className="col-span-2 whitespace-pre-wrap rounded bg-gray-50 p-2 text-xs">
                  {anticipo.notas}
                </dd>
              </>
            )}
          </dl>
        </div>

        <div className="overflow-hidden rounded border bg-white">
          <h2 className="border-b px-6 py-4 text-lg font-semibold">Liquidaciones</h2>
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
              <tr>
                <th className="px-4 py-2">Factura</th>
                <th className="px-4 py-2">Fecha</th>
                <th className="px-4 py-2 text-right">Importe</th>
              </tr>
            </thead>
            <tbody>
              {anticipo.liquidaciones.map((l) => (
                <tr key={l.id} className="border-t">
                  <td className="px-4 py-2 font-mono text-xs">{l.factura_id}</td>
                  <td className="px-4 py-2">{l.fecha_aplicacion}</td>
                  <td className="px-4 py-2 text-right font-mono">{l.importe_aplicado}</td>
                </tr>
              ))}
              {anticipo.liquidaciones.length === 0 && (
                <tr>
                  <td colSpan={3} className="px-4 py-8 text-center text-gray-400">
                    Sin liquidaciones aún.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {anticipo.estado !== "totalmente_aplicado" && (
        <form
          onSubmit={onLiquidar}
          className="space-y-4 rounded border border-green-200 bg-green-50/50 p-6"
        >
          <h3 className="font-semibold text-green-900">Liquidar contra factura</h3>
          <p className="text-xs text-green-700">
            Genera asiento Debe{" "}
            {anticipo.tipo === "CLIENTE" ? "430" : "410"} | Haber{" "}
            {anticipo.tipo === "CLIENTE" ? "438" : "407"} por el importe aplicado.
          </p>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-semibold text-gray-600">
                Factura (UUID)
              </label>
              <input
                type="text"
                required
                className="mt-1 w-full rounded border bg-white p-2 text-sm font-mono"
                value={facturaId}
                onChange={(e) => setFacturaId(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600">
                Importe aplicado (€)
              </label>
              <input
                type="text"
                required
                pattern="^\d+(\.\d{1,4})?$"
                className="mt-1 w-full rounded border bg-white p-2 text-sm font-mono"
                value={importeAplicado}
                onChange={(e) => setImporteAplicado(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600">
                Fecha aplicación
              </label>
              <input
                type="date"
                required
                className="mt-1 w-full rounded border bg-white p-2 text-sm"
                value={fechaAplicacion}
                onChange={(e) => setFechaAplicacion(e.target.value)}
              />
            </div>
          </div>
          <button
            type="submit"
            disabled={procesando}
            className="rounded bg-green-600 px-4 py-2 text-sm font-semibold text-white hover:bg-green-700 disabled:opacity-50"
          >
            {procesando ? "Liquidando..." : "Liquidar"}
          </button>
        </form>
      )}
    </div>
  );
}