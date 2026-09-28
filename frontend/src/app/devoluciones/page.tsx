"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  importarFicheroR19,
  listarDevoluciones,
  formatearImporte,
  type Devolucion,
  type ResultadoImport,
} from "../../components/treasury/api";

export default function DevolucionesPage() {
  const [devoluciones, setDevoluciones] = useState<Devolucion[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [resultado, setResultado] = useState<ResultadoImport | null>(null);
  const ficheroRef = useRef<HTMLInputElement>(null);

  const recargar = useCallback(async () => {
    try {
      const lista = await listarDevoluciones();
      setDevoluciones(lista.items);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }, []);

  useEffect(() => {
    recargar();
  }, [recargar]);

  async function subir() {
    const fichero = ficheroRef.current?.files?.[0];
    if (!fichero) return;
    setResultado(null);
    setError(null);
    try {
      setResultado(await importarFicheroR19(fichero));
      await recargar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }

  return (
    <main className="p-6 max-w-4xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Devoluciones</h1>

      <section className="border rounded p-4 mb-4 flex items-center gap-2">
        <input
          ref={ficheroRef}
          type="file"
          accept=".19"
          className="text-sm"
        />
        <button
          className="bg-blue-600 text-white rounded px-4 py-2 text-sm"
          onClick={subir}
        >
          Importar R19/C19
        </button>
      </section>

      {resultado && (
        <p className="mb-4 text-sm">
          Procesadas: <strong>{resultado.procesadas}</strong> · Rechazadas:{" "}
          <strong>{resultado.rechazadas.length}</strong>
          {resultado.rechazadas.length > 0 && (
            <span className="text-red-600">
              {" "}
              ({resultado.rechazadas.map((r) => r.code).join(", ")})
            </span>
          )}
        </p>
      )}

      {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

      <section className="border rounded">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left border-b">
              <th className="p-2">Código</th>
              <th>Recibo</th>
              <th>Importe</th>
              <th>Gastos</th>
              <th>Fecha registro</th>
              <th>Reclamación</th>
            </tr>
          </thead>
          <tbody>
            {devoluciones.map((d) => (
              <tr key={d.id} className="border-b">
                <td className="p-2">
                  <a className="text-blue-600 underline" href={`/devoluciones/${d.id}`}>
                    {d.codigo}
                  </a>
                </td>
                <td>{d.recibo?.recibo_num ?? d.recibo_remesa_id}</td>
                <td>{formatearImporte(d.importe)}</td>
                <td>{formatearImporte(d.importe_gastos)}</td>
                <td>{d.fecha_registro}</td>
                <td>{d.estado_reclamacion}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}