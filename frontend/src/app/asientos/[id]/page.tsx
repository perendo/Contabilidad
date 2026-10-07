"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { DocumentosAsiento } from "../../../components/documentos/DocumentosAsiento";
import { ApiError } from "../../../components/treasury/api";
import { get, post } from "../../../services/client";

interface Linea {
  account_id: number | null;
  account_code: string;
  debit: string;
  credit: string;
  detail: string | null;
}

interface Detalle {
  id: string;
  numero: number | null;
  fecha: string;
  concepto: string;
  estado: string;
  lineas: Linea[];
}

export default function DetalleAsientoPage() {
  const params = useParams<{ id: string }>();
  const [detalle, setDetalle] = useState<Detalle | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    try {
      setDetalle(await get<Detalle>(`/api/v1/journal/entries/${params.id}`));
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    }
  }, [params.id]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  async function anular() {
    if (!window.confirm("¿Anular el asiento con rectificativo?")) return;
    setError(null);
    try {
      await post(`/api/v1/journal/entries/${params.id}/reverse`, {});
      await cargar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    }
  }

  async function asentar() {
    if (!window.confirm("¿Asentar este asiento en el libro diario?")) return;
    setError(null);
    try {
      await post(`/api/v1/journal/entries/${params.id}/post`, {});
      await cargar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    }
  }

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Asiento</h1>
      {error && <p className="text-red-600 mb-4">{error}</p>}
      {detalle && (
        <>
          <p className="mb-2">
            Nº <span className="font-mono">{detalle.numero ?? "borrador"}</span> ·{" "}
            {detalle.fecha} · {detalle.concepto} ·{" "}
            <span className={detalle.estado === "CANCELLED" ? "text-red-600" : ""}>
              {detalle.estado}
            </span>
          </p>
          {detalle.estado === "DRAFT" && (
            <button
              onClick={asentar}
              className="bg-blue-600 text-white rounded px-3 py-1 mb-4"
            >
              Asentar en el libro diario
            </button>
          )}
          {detalle.estado === "POSTED" && (
            <button onClick={anular} className="bg-red-600 text-white rounded px-3 py-1 mb-4">
              Anular con rectificativo
            </button>
          )}
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b">
                <th className="text-left p-2">Cuenta</th>
                <th className="text-right p-2">Debe</th>
                <th className="text-right p-2">Haber</th>
              </tr>
            </thead>
            <tbody>
              {detalle.lineas.map((l, i) => (
                <tr key={i} className="border-b">
                  <td className="p-2 font-mono">{l.account_code}</td>
                  <td className="text-right p-2 font-mono">{l.debit}</td>
                  <td className="text-right p-2 font-mono">{l.credit}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {/* SPEC-030: la seccion declara que los adjuntos son opcionales y no
              toca las cifras del asiento (FR-015, FR-020). El estado del
              asiento se pasa desde el `Detalle` ya cargado, sin un segundo
              fetch. */}
          <DocumentosAsiento
            asientoId={detalle.id}
            estadoAsiento={detalle.estado}
          />
        </>
      )}
    </main>
  );
}
