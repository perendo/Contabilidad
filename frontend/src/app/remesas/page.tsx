"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  formatearImporte,
  listarRemesas,
  type Remesa,
} from "../../components/treasury/api";

const PAGINA_TAM = 20;

export default function ListadoRemesasPage() {
  const [items, setItems] = useState<Remesa[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [estado, setEstado] = useState("");
  const [ejercicio, setEjercicio] = useState("");
  const [formato, setFormato] = useState("");
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setError(null);
    try {
      const resultado = await listarRemesas({
        estado: estado || undefined,
        formato: formato || undefined,
        limit: PAGINA_TAM,
        offset,
      });
      const itemsFiltrados =
        ejercicio && ejercicio !== ""
          ? resultado.items.filter(
              (remesa) => String(remesa.ejercicio) === ejercicio
            )
          : resultado.items;
      setItems(itemsFiltrados);
      setTotal(ejercicio && ejercicio !== "" ? itemsFiltrados.length : resultado.total);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }, [estado, formato, ejercicio, offset]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <div className="flex items-baseline justify-between mb-4">
        <h1 className="text-xl font-semibold">Remesas de cobros</h1>
        <Link
          href="/remesas/nueva"
          className="bg-blue-600 text-white rounded px-3 py-1"
        >
          Nueva remesa
        </Link>
      </div>

      <section className="border rounded p-3 mb-4 flex gap-4">
        <label className="block text-sm">
          Estado
          <select
            className="border rounded p-1"
            value={estado}
            onChange={(e) => {
              setEstado(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">Todos</option>
            <option value="borrador">Borrador</option>
            <option value="emitida">Emitida</option>
            <option value="cobrada">Cobrada</option>
            <option value="devuelta">Devuelta</option>
          </select>
        </label>
        <label className="block text-sm">
          Ejercicio
          <select
            className="border rounded p-1"
            value={ejercicio}
            onChange={(e) => {
              setEjercicio(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">Todos</option>
            {Array.from({ length: 3 }, (_, i) => 2026 - i).map((anio) => (
              <option key={anio} value={String(anio)}>
                {anio}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm">
          Formato
          <select
            className="border rounded p-1"
            value={formato}
            onChange={(e) => {
              setFormato(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">Todos</option>
            <option value="SEPA_DD">SEPA DD</option>
            <option value="CSB_19_19">CSB 19.19</option>
          </select>
        </label>
      </section>

      {error && <p className="text-red-600 text-sm mb-3">Error: {error}</p>}

      <section className="border rounded overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left border-b">
              <th className="p-2">Número</th>
              <th>Ejercicio</th>
              <th>Estado</th>
              <th>Formato</th>
              <th>Tipo</th>
              <th>Fecha cargo</th>
              <th>Importe</th>
              <th>Recibos</th>
            </tr>
          </thead>
          <tbody>
            {items.map((remesa) => (
              <tr key={remesa.id} className="border-b">
                <td className="p-2">
                  <a
                    href={`/remesas/${remesa.id}`}
                    className="text-blue-600 underline"
                  >
                    {remesa.numero_remesa}
                  </a>
                </td>
                <td>{remesa.ejercicio}</td>
                <td>{remesa.estado}</td>
                <td>{remesa.formato}</td>
                <td>{remesa.tipo_adeudo}</td>
                <td>{remesa.fecha_cargo ?? "varias"}</td>
                <td>{formatearImporte(remesa.importe_total)}</td>
                <td>{remesa.n_recibos ?? 0}</td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td className="p-2" colSpan={8}>
                  Sin remesas en esta vista.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      <section className="mt-3 flex justify-between text-sm">
        <button
          className="border rounded px-3 py-1"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - PAGINA_TAM))}
        >
          Anterior
        </button>
        <span>
          {items.length} de {total}
        </span>
        <button
          className="border rounded px-3 py-1"
          disabled={offset + PAGINA_TAM >= total}
          onClick={() => setOffset(offset + PAGINA_TAM)}
        >
          Siguiente
        </button>
      </section>
    </main>
  );
}