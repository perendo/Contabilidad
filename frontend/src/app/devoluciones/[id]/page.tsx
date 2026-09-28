"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import {
  ApiError,
  crearReclamacion,
  formatearImporte,
  obtenerDevolucion,
  type Devolucion,
} from "../../../components/treasury/api";

const ACCIONES: { accion: string; label: string; desde: string[] }[] = [
  { accion: "abrir", label: "Abrir", desde: ["sin_reclamacion"] },
  { accion: "en_curso", label: "En curso", desde: ["reclamada"] },
  { accion: "resolver", label: "Resolver", desde: ["reclamada"] },
  { accion: "desestimar", label: "Desestimar", desde: ["reclamada"] },
];

export default function DetalleDevolucionPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [devolucion, setDevolucion] = useState<Devolucion | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [accion, setAccion] = useState("abrir");
  const [observaciones, setObservaciones] = useState("");

  const recargar = useCallback(async () => {
    try {
      setDevolucion(await obtenerDevolucion(id));
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }, [id]);

  useEffect(() => {
    recargar();
  }, [recargar]);

  async function enviarReclamacion() {
    try {
      await crearReclamacion(id, accion, observaciones || undefined);
      setObservaciones("");
      await recargar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }

  if (error) {
    return <p className="p-6 text-red-600">Error: {error}</p>;
  }
  if (!devolucion) {
    return <p className="p-6">Cargando devolución…</p>;
  }

  const accionable = ACCIONES.find(
    (a) => a.accion === accion && a.desde.includes(devolucion.estado_reclamacion)
  );

  return (
    <main className="p-6 max-w-4xl mx-auto">
      <nav className="text-sm mb-3">
        <Link href="/devoluciones" className="text-blue-600 underline">
          ← Devoluciones
        </Link>
      </nav>
      <h1 className="text-xl font-semibold mb-4">
        Devolución {devolucion.codigo} · {devolucion.id.slice(0, 8)}
      </h1>

      <section className="border rounded p-4 mb-4 grid grid-cols-2 gap-2 text-sm">
        <p>
          Recibo: {devolucion.recibo?.recibo_num ?? devolucion.recibo_remesa_id}
        </p>
        <p>Estado recibo: {devolucion.recibo?.estado ?? "—"}</p>
        <p>Importe: {formatearImporte(devolucion.importe)}</p>
        <p>Gastos: {formatearImporte(devolucion.importe_gastos)}</p>
        <p>Fecha registro: {devolucion.fecha_registro}</p>
        <p>Fecha cargo: {devolucion.fecha_cargo_original}</p>
        <p>
          Asiento reversión:{" "}
          {devolucion.asiento_reversal_id?.slice(0, 8) ?? "—"}
        </p>
        <p>Reclamación: {devolucion.estado_reclamacion}</p>
      </section>
      <p className="text-sm mb-4">{devolucion.motivo}</p>

      <section className="border rounded p-4 mb-4">
        <h2 className="font-semibold mb-2">Reclamaciones</h2>
        {devolucion.reclamaciones?.length ? (
          <ul className="text-sm space-y-1 mb-3">
            {devolucion.reclamaciones.map((r) => (
              <li key={r.id}>
                {r.estado} · {r.fecha_registro}
                {r.observaciones && ` — ${r.observaciones}`}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-500 mb-3">Sin reclamaciones.</p>
        )}
        <div className="flex items-center gap-2">
          <select
            value={accion}
            onChange={(e) => setAccion(e.target.value)}
            className="border rounded px-2 py-1 text-sm"
          >
            {ACCIONES.map((a) => (
              <option key={a.accion} value={a.accion}>
                {a.label}
              </option>
            ))}
          </select>
          <input
            value={observaciones}
            onChange={(e) => setObservaciones(e.target.value)}
            placeholder="Observaciones"
            className="border rounded px-2 py-1 text-sm flex-1"
          />
          <button
            disabled={!accionable}
            className="bg-blue-600 disabled:bg-slate-300 text-white rounded px-4 py-2 text-sm"
            onClick={enviarReclamacion}
          >
            Aplicar
          </button>
        </div>
      </section>
    </main>
  );
}