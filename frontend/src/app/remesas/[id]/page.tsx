"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import {
  ApiError,
  cobrarRecibo,
  descargarFichero,
  emitirRemesa,
  formatearImporte,
  obtenerRemesa,
  type Remesa,
} from "../../../components/treasury/api";

export default function DetalleRemesaPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [remesa, setRemesa] = useState<Remesa | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [avisos, setAvisos] = useState<Record<string, string>>({});

  const recargar = useCallback(async () => {
    try {
      setRemesa(await obtenerRemesa(id));
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }, [id]);

  useEffect(() => {
    recargar();
  }, [recargar]);

  async function emitir() {
    try {
      await emitirRemesa(id);
      await recargar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }

  async function cobrar(reciboId: string) {
    try {
      const resultado = await cobrarRecibo(id, reciboId);
      setAvisos((previos) => ({
        ...previos,
        [reciboId]: resultado.asiento_id
          ? "Cobrado (asiento " + resultado.asiento_id.slice(0, 8) + ")"
          : "Cobrado",
      }));
      await recargar();
    } catch (e) {
      if (e instanceof ApiError) {
        setAvisos((previos) => ({ ...previos, [reciboId]: e.message }));
      }
    }
  }

  async function descargar() {
    try {
      await descargarFichero(id);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }

  if (error) {
    return <p className="p-6 text-red-600">Error: {error}</p>;
  }
  if (!remesa) {
    return <p className="p-6">Cargando remesa…</p>;
  }

  return (
    <main className="p-6 max-w-4xl mx-auto">
      <nav className="text-sm mb-3">
        <Link href="/remesas" className="text-blue-600 underline">
          ← Remesas
        </Link>
      </nav>
      <h1 className="text-xl font-semibold mb-4">
        Remesa {remesa.numero_remesa} · {remesa.ejercicio}
      </h1>

      <section className="border rounded p-4 mb-4 grid grid-cols-2 gap-2 text-sm">
        <p>Estado: <strong>{remesa.estado}</strong></p>
        <p>Formato: {remesa.formato}</p>
        <p>Tipo de adeudo: {remesa.tipo_adeudo}</p>
        <p>Importe total: {formatearImporte(remesa.importe_total)}</p>
        <p>
          Fecha de emisión: {remesa.fecha_emision ?? "—"}
        </p>
        <p>Fecha de cargo: {remesa.fecha_cargo ?? "varias fechas"}</p>
      </section>

      <section className="mb-4 flex gap-2">
        {remesa.estado === "borrador" && (
          <button
            className="bg-blue-600 text-white rounded px-4 py-2"
            onClick={emitir}
          >
            Emitir
          </button>
        )}
        {remesa.estado !== "borrador" && (
          <button
            className="bg-slate-800 text-white rounded px-4 py-2"
            onClick={descargar}
          >
            Descargar fichero
          </button>
        )}
      </section>

      <section className="border rounded">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left border-b">
              <th className="p-2">Recibo</th>
              <th>Fecha cargo</th>
              <th>Importe</th>
              <th>Estado</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {(remesa.recibos ?? []).map((recibo) => (
              <tr key={recibo.id} className="border-b">
                <td className="p-2">{recibo.recibo_num}</td>
                <td>{recibo.fecha_cargo}</td>
                <td>{formatearImporte(recibo.importe)}</td>
                <td>{recibo.estado}</td>
                <td>
                  {recibo.estado === "remesado" && (
                    <button
                      className="bg-emerald-600 text-white rounded px-2 py-1 text-xs"
                      onClick={() => cobrar(recibo.id)}
                    >
                      Cobrar
                    </button>
                  )}
                  {avisos[recibo.id] && (
                    <span className="ml-2 text-xs text-emerald-700">
                      {avisos[recibo.id]}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}