"use client";

import { useCallback, useEffect, useState } from "react";

import {
  formatearImporte,
  obtenerLibro,
  type LibroIva,
} from "../../components/vat/api";
import { ApiError } from "../../components/treasury/api";

const TIPOS = ["emitidas", "recibidas", "intracomunitarias"];

export default function LibrosIvaPage() {
  const [tipo, setTipo] = useState("emitidas");
  const [ejercicio, setEjercicio] = useState(2026);
  const [periodo, setPeriodo] = useState(1);
  const [tipoPeriodo, setTipoPeriodo] = useState("TRIMESTRE");
  const [libro, setLibro] = useState<LibroIva | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setError(null);
    try {
      setLibro(await obtenerLibro(tipo, ejercicio, periodo, tipoPeriodo));
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }, [tipo, ejercicio, periodo, tipoPeriodo]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Libros de IVA</h1>
      <div className="flex flex-wrap items-end gap-3 mb-4">
        <label className="block">
          <span className="text-sm">Tipo</span>
          <select
            value={tipo}
            onChange={(e) => setTipo(e.target.value)}
            className="border rounded px-2 py-1 mt-1"
          >
            {TIPOS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="text-sm">Ejercicio</span>
          <input
            type="number"
            value={ejercicio}
            onChange={(e) => setEjercicio(Number(e.target.value))}
            className="border rounded px-2 py-1 mt-1 w-28"
          />
        </label>
        <label className="block">
          <span className="text-sm">Periodo</span>
          <input
            type="number"
            value={periodo}
            onChange={(e) => setPeriodo(Number(e.target.value))}
            className="border rounded px-2 py-1 mt-1 w-20"
          />
        </label>
        <select
          value={tipoPeriodo}
          onChange={(e) => setTipoPeriodo(e.target.value)}
          className="border rounded px-2 py-1"
        >
          <option value="TRIMESTRE">TRIMESTRE</option>
          <option value="MES">MES</option>
        </select>
      </div>

      {error && <p className="text-red-600 mb-4">{error}</p>}

      {libro && (
        <>
          <p className="text-sm mb-3">
            {libro.n_operaciones} operaciones · Base {formatearImporte(libro.total_base)} ·
            Cuota {formatearImporte(libro.total_cuota)} · Recargo{" "}
            {formatearImporte(libro.total_recargo)}
          </p>
          <table className="w-full text-sm border">
            <thead className="bg-gray-100">
              <tr>
                <th className="text-left p-2">NIF</th>
                <th className="text-left p-2">Factura</th>
                <th className="text-left p-2">Fecha</th>
                <th className="text-right p-2">Base</th>
                <th className="text-right p-2">Cuota</th>
                <th className="text-right p-2">Tipo</th>
                <th className="text-right p-2">Recargo</th>
                <th className="text-left p-2">303</th>
              </tr>
            </thead>
            <tbody>
              {libro.operaciones.map((op, i) => (
                <tr key={`${op.factura_id}-${i}`} className="border-t">
                  <td className="p-2">{op.nif_tercero}</td>
                  <td className="p-2">{op.num_factura}</td>
                  <td className="p-2">{op.fecha_expedicion}</td>
                  <td className="p-2 text-right">{formatearImporte(op.base)}</td>
                  <td className="p-2 text-right">{formatearImporte(op.cuota)}</td>
                  <td className="p-2 text-right">{op.tipo_iva}</td>
                  <td className="p-2 text-right">{formatearImporte(op.recargo_cuota)}</td>
                  <td className="p-2">{op.incluir_303 ? "sí" : "diferido"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </main>
  );
}