"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  DetallePrevision,
  esNegativo,
  formatearImporte,
  obtenerPrevision,
  regenerarPrevision,
} from "@/components/cashflow/api";

export default function DetallePrevisionPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [detalle, setDetalle] = useState<DetallePrevision | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [regenerando, setRegenerando] = useState(false);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      setDetalle(await obtenerPrevision(id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo cargar la previsión");
    } finally {
      setCargando(false);
    }
  }, [id]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const regenerar = async () => {
    setRegenerando(true);
    setError(null);
    try {
      await regenerarPrevision(id, {});
      await cargar();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo regenerar la previsión");
    } finally {
      setRegenerando(false);
    }
  };

  if (cargando) {
    return <div className="p-8 text-center text-gray-500">Cargando previsión…</div>;
  }

  if (error && !detalle) {
    return (
      <div className="space-y-4">
        <div className="rounded border border-red-200 bg-red-50 p-4 text-red-700">{error}</div>
        <Link href="/tesoreria/previsiones" className="text-sm text-blue-600 hover:underline">
          ← Volver al listado
        </Link>
      </div>
    );
  }

  if (!detalle) return null;

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Previsión nº {detalle.numero_prevision}</h1>
          <p className="text-sm text-gray-500">
            {detalle.desde_fecha} → {detalle.hasta_fecha} · granularidad{" "}
            {detalle.granularidad} · origen del saldo inicial:{" "}
            {detalle.origen_saldo_inicial ?? "—"}
          </p>
        </div>
        <div className="flex gap-3">
          <Link
            href="/tesoreria/previsiones"
            className="rounded border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
          >
            Volver
          </Link>
          <button
            onClick={regenerar}
            disabled={regenerando}
            className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {regenerando ? "Regenerando…" : "Regenerar"}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 p-4 text-red-700">{error}</div>
      )}

      <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <div className="rounded border bg-white p-4">
          <div className="text-xs uppercase text-gray-500">Saldo inicial</div>
          <div className="font-mono text-xl">{formatearImporte(detalle.saldo_inicial)}</div>
        </div>
        <div className="rounded border bg-white p-4">
          <div className="text-xs uppercase text-gray-500">Saldo final proyectado</div>
          <div
            className={`font-mono text-xl font-bold ${
              esNegativo(detalle.saldo_final) ? "text-red-600" : "text-green-700"
            }`}
          >
            {formatearImporte(detalle.saldo_final)}
          </div>
        </div>
        <div className="rounded border bg-white p-4">
          <div className="text-xs uppercase text-gray-500">Movimientos</div>
          <div className="font-mono text-xl">{detalle.movimientos.length}</div>
        </div>
        <div className="rounded border bg-white p-4">
          <div className="text-xs uppercase text-gray-500">Alertas abiertas</div>
          <div className="font-mono text-xl">
            {detalle.alertas.filter((a) => a.estado === "abierta").length}
          </div>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Proyección por periodo</h2>
        <div className="overflow-x-auto rounded border bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b bg-gray-100 text-xs uppercase text-gray-600">
              <tr>
                <th className="p-3">Periodo</th>
                <th className="p-3 text-right">Cobros</th>
                <th className="p-3 text-right">Pagos</th>
                <th className="p-3 text-right">Neto</th>
                <th className="p-3 text-right">Saldo acumulado</th>
              </tr>
            </thead>
            <tbody>
              {detalle.buckets.map((bucket) => (
                <tr
                  key={bucket.fecha}
                  className={`border-b ${bucket.alerta ? "bg-red-50" : "hover:bg-gray-50"}`}
                >
                  <td className="p-3 font-medium">
                    {bucket.fecha}
                    {bucket.alerta && (
                      <span className="ml-2 rounded bg-red-600 px-1.5 py-0.5 text-xs text-white">
                        déficit
                      </span>
                    )}
                  </td>
                  <td className="p-3 text-right font-mono text-green-700">
                    {formatearImporte(bucket.cobros)}
                  </td>
                  <td className="p-3 text-right font-mono text-red-600">
                    {formatearImporte(bucket.pagos)}
                  </td>
                  <td className="p-3 text-right font-mono">{formatearImporte(bucket.neto)}</td>
                  <td
                    className={`p-3 text-right font-mono font-semibold ${
                      esNegativo(bucket.saldo_acumulado) ? "text-red-700" : ""
                    }`}
                  >
                    {formatearImporte(bucket.saldo_acumulado)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Movimientos proyectados</h2>
        <div className="overflow-x-auto rounded border bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b bg-gray-100 text-xs uppercase text-gray-600">
              <tr>
                <th className="p-3">Fecha</th>
                <th className="p-3">Tipo</th>
                <th className="p-3">Origen</th>
                <th className="p-3">Concepto</th>
                <th className="p-3 text-right">Importe</th>
              </tr>
            </thead>
            <tbody>
              {detalle.movimientos.length === 0 ? (
                <tr>
                  <td colSpan={5} className="p-6 text-center text-gray-400">
                    Sin movimientos proyectados
                  </td>
                </tr>
              ) : (
                detalle.movimientos.map((movimiento) => (
                  <tr key={movimiento.id} className="border-b hover:bg-gray-50">
                    <td className="p-3">{movimiento.fecha_prevista ?? "—"}</td>
                    <td className="p-3">{movimiento.tipo}</td>
                    <td className="p-3 text-gray-600">{movimiento.origen}</td>
                    <td className="p-3">{movimiento.concepto ?? "—"}</td>
                    <td className="p-3 text-right font-mono">
                      {formatearImporte(movimiento.importe)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {detalle.excluidos.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold">Excluidos de la proyección</h2>
          <div className="overflow-x-auto rounded border bg-amber-50">
            <table className="w-full text-left text-sm">
              <thead className="border-b bg-gray-100 text-xs uppercase text-gray-600">
                <tr>
                  <th className="p-3">Origen</th>
                  <th className="p-3">Concepto</th>
                  <th className="p-3">Motivo</th>
                  <th className="p-3 text-right">Importe</th>
                </tr>
              </thead>
              <tbody>
                {detalle.excluidos.map((excluido, indice) => (
                  <tr key={indice} className="border-b">
                    <td className="p-3">{excluido.origen}</td>
                    <td className="p-3">{excluido.concepto ?? "—"}</td>
                    <td className="p-3 font-medium">{excluido.motivo}</td>
                    <td className="p-3 text-right font-mono">
                      {formatearImporte(excluido.importe)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {detalle.alertas.length > 0 && (
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Alertas de liquidez</h2>
            <Link
              href="/tesoreria/alertas"
              className="text-sm text-blue-600 hover:underline"
            >
              Gestionar alertas →
            </Link>
          </div>
          <div className="overflow-x-auto rounded border bg-white">
            <table className="w-full text-left text-sm">
              <thead className="border-b bg-gray-100 text-xs uppercase text-gray-600">
                <tr>
                  <th className="p-3">Periodo</th>
                  <th className="p-3 text-right">Saldo proyectado</th>
                  <th className="p-3 text-right">Déficit</th>
                  <th className="p-3">Acción sugerida</th>
                  <th className="p-3">Estado</th>
                </tr>
              </thead>
              <tbody>
                {detalle.alertas.map((alerta) => (
                  <tr key={alerta.id} className="border-b hover:bg-gray-50">
                    <td className="p-3">{alerta.fecha}</td>
                    <td className="p-3 text-right font-mono text-red-700">
                      {formatearImporte(alerta.saldo_proyectado)}
                    </td>
                    <td className="p-3 text-right font-mono">
                      {formatearImporte(alerta.importe_deficit)}
                    </td>
                    <td className="p-3">{alerta.accion_sugerida}</td>
                    <td className="p-3">{alerta.estado}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
