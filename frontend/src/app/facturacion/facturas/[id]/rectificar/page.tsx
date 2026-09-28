"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import {
  formatearImporte,
  listarSeries,
  obtenerFactura,
  rectificarFactura,
  type Factura,
  type SerieFactura,
} from "../../../../../components/invoicing/api";
import { ApiError } from "../../../../../components/treasury/api";

export default function RectificarFacturaPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;

  const [factura, setFactura] = useState<Factura | null>(null);
  const [series, setSeries] = useState<SerieFactura[]>([]);
  const [serieId, setSerieId] = useState("");
  const [motivo, setMotivo] = useState("Rectificación");
  const [parcial, setParcial] = useState(false);
  const [precio, setPrecio] = useState("0.0000");
  const [error, setError] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const cargar = useCallback(async () => {
    try {
      const [f, s] = await Promise.all([obtenerFactura(id), listarSeries()]);
      setFactura(f);
      setSeries(s);
      if (s.length > 0) setSerieId(s[0].id);
      if (f.lineas.length === 1) setPrecio(f.lineas[0].precio_unitario);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }, [id]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  async function submit() {
    setError(null);
    setOcupado(true);
    try {
      const lineas = parcial
        ? [
            {
              descripcion: factura?.lineas[0]?.descripcion ?? "Abono",
              cantidad: "1",
              precio_unitario: precio,
              tipo_iva: factura?.lineas[0]?.tipo_iva ?? "21",
            },
          ]
        : undefined;
      const abono = await rectificarFactura(id, {
        serie_id: serieId,
        motivo,
        lineas,
      });
      router.push(`/facturacion/facturas/${abono.id}`);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    } finally {
      setOcupado(false);
    }
  }

  if (!factura) {
    return (
      <main className="p-6 max-w-3xl mx-auto">
        {error ? <p className="text-red-600">{error}</p> : <p>Cargando…</p>}
      </main>
    );
  }

  return (
    <main className="p-6 max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">
          Rectificar factura {factura.numero}
        </h1>
        <Link
          href={`/facturacion/facturas/${id}`}
          className="text-blue-700 underline"
        >
          Volver
        </Link>
      </div>

      {error && <p className="text-red-600 mb-4">{error}</p>}

      <p className="text-sm mb-4">
        Total original: <strong>{formatearImporte(factura.importe_total)}</strong>
      </p>

      <label className="block mb-4">
        <span className="text-sm">Motivo</span>
        <input
          value={motivo}
          onChange={(e) => setMotivo(e.target.value)}
          className="border rounded px-2 py-1 mt-1 w-full"
        />
      </label>

      <label className="block mb-4">
        <span className="text-sm">Serie del abono</span>
        <select
          value={serieId}
          onChange={(e) => setSerieId(e.target.value)}
          className="border rounded px-2 py-1 mt-1 w-full"
        >
          {series.map((s) => (
            <option key={s.id} value={s.id}>
              {s.codigo} ({s.estado})
            </option>
          ))}
        </select>
      </label>

      <label className="flex items-center gap-2 mb-4 text-sm">
        <input
          type="checkbox"
          checked={parcial}
          onChange={(e) => setParcial(e.target.checked)}
        />
        Rectificación parcial (indica el importe a abonar)
      </label>

      {parcial && (
        <label className="block mb-4">
          <span className="text-sm">Precio unitario del abono</span>
          <input
            value={precio}
            onChange={(e) => setPrecio(e.target.value)}
            className="border rounded px-2 py-1 mt-1 w-40"
          />
        </label>
      )}

      <button
        onClick={submit}
        disabled={ocupado}
        className="bg-amber-600 text-white rounded px-4 py-2 disabled:opacity-50"
      >
        {ocupado ? "Generando…" : "Generar rectificativa"}
      </button>
    </main>
  );
}
