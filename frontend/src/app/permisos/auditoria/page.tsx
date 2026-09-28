"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  obtenerAuditoria,
  type EventoAuditoria,
} from "../../../components/rbac/api";

export default function AuditoriaPage() {
  const [items, setItems] = useState<EventoAuditoria[]>([]);
  const [total, setTotal] = useState(0);
  const [resultado, setResultado] = useState("");
  const [modulo, setModulo] = useState("");
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);

  const consultar = useCallback(async () => {
    setError(null);
    try {
      const cuerpo = await obtenerAuditoria({
        resultado: resultado || undefined,
        modulo: modulo || undefined,
        page,
        page_size: 20,
      });
      setItems(cuerpo.items);
      setTotal(cuerpo.total);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    }
  }, [resultado, modulo, page]);

  useEffect(() => {
    consultar();
  }, [consultar]);

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">Auditoría de accesos</h1>
        <Link className="text-blue-600 underline text-sm" href="/permisos">
          Volver a la matriz
        </Link>
      </div>

      <div className="flex items-center gap-3 mb-4">
        <select
          value={resultado}
          onChange={(e) => {
            setResultado(e.target.value);
            setPage(1);
          }}
          className="border rounded px-3 py-1"
        >
          <option value="">Todos los resultados</option>
          <option value="allow">Permitido</option>
          <option value="deny">Denegado</option>
        </select>
        <input
          value={modulo}
          onChange={(e) => {
            setModulo(e.target.value);
            setPage(1);
          }}
          placeholder="Módulo (p. ej. acct)"
          className="border rounded px-3 py-1"
        />
      </div>

      {error && <p className="text-red-600 mb-4">{error}</p>}

      <p className="text-sm text-gray-600 mb-2">Total: {total}</p>

      <table className="w-full text-sm border rounded">
        <thead>
          <tr className="text-left bg-gray-100">
            <th className="p-2">Fecha (UTC)</th>
            <th className="p-2">Usuario</th>
            <th className="p-2">Módulo</th>
            <th className="p-2">Operación</th>
            <th className="p-2">Resultado</th>
            <th className="p-2">Motivo</th>
            <th className="p-2">IP</th>
          </tr>
        </thead>
        <tbody>
          {items.map((e) => (
            <tr key={e.evento_id} className="border-t">
              <td className="p-2 font-mono">{e.timestamp_utc}</td>
              <td className="p-2">{e.usuario_id}</td>
              <td className="p-2 font-mono">{e.modulo}</td>
              <td className="p-2">{e.operacion}</td>
              <td className="p-2">{e.resultado}</td>
              <td className="p-2">{e.motivo}</td>
              <td className="p-2 font-mono">{e.ip ?? "-"}</td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td colSpan={7} className="p-2 text-gray-500">
                Sin eventos.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <div className="flex items-center gap-3 mt-4">
        <button
          type="button"
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          disabled={page === 1}
          className="border rounded px-3 py-1 disabled:opacity-50"
        >
          Anterior
        </button>
        <span className="text-sm">Página {page}</span>
        <button
          type="button"
          onClick={() => setPage((p) => p + 1)}
          disabled={page * 20 >= total}
          className="border rounded px-3 py-1 disabled:opacity-50"
        >
          Siguiente
        </button>
      </div>
    </main>
  );
}
