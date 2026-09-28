"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import {
  anularFactura,
  eliminarFactura,
  emitirFactura,
  formatearImporte,
  obtenerFactura,
  type Factura,
} from "../../../../components/invoicing/api";
import { ApiError } from "../../../../components/treasury/api";

export default function FacturaDetallePage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [factura, setFactura] = useState<Factura | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const cargar = useCallback(async () => {
    setError(null);
    try {
      setFactura(await obtenerFactura(id));
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }, [id]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  async function accion(fn: (id: string) => Promise<unknown>) {
    setError(null);
    setOcupado(true);
    try {
      await fn(id);
      await cargar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    } finally {
      setOcupado(false);
    }
  }

  if (!factura) {
    return (
      <main className="p-6 max-w-4xl mx-auto">
        {error ? <p className="text-red-600">{error}</p> : <p>Cargando…</p>}
      </main>
    );
  }

  return (
    <main className="p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">
          Factura {factura.numero ?? "(borrador)"}
        </h1>
        <Link href="/facturacion/facturas" className="text-blue-700 underline">
          Volver
        </Link>
      </div>

      {error && <p className="text-red-600 mb-4">{error}</p>}

      <div className="border rounded p-4 text-sm mb-4 grid grid-cols-2 gap-2">
        <p>
          <strong>Estado:</strong> {factura.estado}
        </p>
        <p>
          <strong>Tipo:</strong> {factura.tipo}
        </p>
        <p>
          <strong>Fecha:</strong> {factura.fecha}
        </p>
        <p>
          <strong>Ejercicio:</strong> {factura.ejercicio}
        </p>
        <p>
          <strong>Base:</strong> {formatearImporte(factura.importe_base)}
        </p>
        <p>
          <strong>IVA:</strong> {formatearImporte(factura.importe_iva)}
        </p>
        <p>
          <strong>Recargo:</strong> {formatearImporte(factura.importe_recargo)}
        </p>
        <p>
          <strong>IRPF:</strong> {formatearImporte(factura.importe_irpf)}
        </p>
        <p className="font-semibold">
          <strong>Total:</strong> {formatearImporte(factura.importe_total)}
        </p>
        <p>
          <strong>Criterio de caja:</strong> {factura.regimen_caja ? "sí" : "no"}
        </p>
        {factura.factura_original_id && (
          <p className="col-span-2 font-mono text-xs">
            Rectifica a: {factura.factura_original_id}
          </p>
        )}
      </div>

      <h2 className="font-medium mb-2">Líneas</h2>
      <table className="w-full text-sm border mb-4">
        <thead className="bg-gray-100">
          <tr>
            <th className="text-left p-2">Descripción</th>
            <th className="text-right p-2">Cantidad</th>
            <th className="text-right p-2">Precio</th>
            <th className="text-right p-2">Base</th>
            <th className="text-right p-2">IVA</th>
          </tr>
        </thead>
        <tbody>
          {factura.lineas.map((l) => (
            <tr key={l.id} className="border-t">
              <td className="p-2">{l.descripcion}</td>
              <td className="p-2 text-right">{l.cantidad}</td>
              <td className="p-2 text-right">{l.precio_unitario}</td>
              <td className="p-2 text-right">{formatearImporte(l.base)}</td>
              <td className="p-2 text-right">
                {l.tipo_iva}% = {formatearImporte(l.cuota_iva)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {factura.asiento && (
        <>
          <h2 className="font-medium mb-2">
            Asiento nº {factura.asiento.numero_asiento}{" "}
            <span className="text-gray-500 text-sm">({factura.asiento.tipo})</span>
          </h2>
          <table className="w-full text-sm border mb-4">
            <thead className="bg-gray-100">
              <tr>
                <th className="text-left p-2">Cuenta</th>
                <th className="text-left p-2">Detalle</th>
                <th className="text-right p-2">Debe</th>
                <th className="text-right p-2">Haber</th>
              </tr>
            </thead>
            <tbody>
              {factura.asiento.lineas.map((l) => (
                <tr key={l.id} className="border-t">
                  <td className="p-2 font-mono">{l.cuenta}</td>
                  <td className="p-2">{l.detalle}</td>
                  <td className="p-2 text-right">{formatearImporte(l.debe)}</td>
                  <td className="p-2 text-right">{formatearImporte(l.haber)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <div className="flex gap-3">
        {factura.estado === "borrador" && (
          <>
            <button
              onClick={() => accion(emitirFactura)}
              disabled={ocupado}
              className="bg-blue-600 text-white rounded px-4 py-2 disabled:opacity-50"
            >
              Emitir
            </button>
            <button
              onClick={() => accion(eliminarFactura)}
              disabled={ocupado}
              className="bg-red-600 text-white rounded px-4 py-2 disabled:opacity-50"
            >
              Eliminar borrador
            </button>
          </>
        )}
        {factura.estado === "emitida" && (
          <>
            <Link
              href={`/facturacion/facturas/${factura.id}/rectificar`}
              className="bg-amber-600 text-white rounded px-4 py-2"
            >
              Rectificar
            </Link>
            <button
              onClick={() => accion(anularFactura)}
              disabled={ocupado}
              className="bg-red-600 text-white rounded px-4 py-2 disabled:opacity-50"
            >
              Anular
            </button>
          </>
        )}
      </div>
    </main>
  );
}
