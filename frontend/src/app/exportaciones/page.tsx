"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  ETIQUETA_ESTADO,
  formatearBytes,
  listarExportaciones,
  type EstadoExportacion,
  type Exportacion,
  type TipoExportacion,
} from "@/components/export/api";

export default function ExportacionesPage() {
  const [items, setItems] = useState<Exportacion[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [tipo, setTipo] = useState<TipoExportacion | "">("");
  const [estado, setEstado] = useState<EstadoExportacion | "">("");
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const datos = await listarExportaciones({
        page,
        page_size: 20,
        tipo: tipo || undefined,
        estado: estado || undefined,
      });
      setItems(datos.items);
      setTotal(datos.total);
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "No se pudieron cargar las exportaciones"
      );
    } finally {
      setCargando(false);
    }
  }, [page, tipo, estado]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const paginas = Math.max(1, Math.ceil(total / 20));

  return (
    <main className="p-6 max-w-6xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Exportaciones</h1>
          <p className="text-sm text-gray-500">
            Copia de seguridad y portabilidad de la empresa activa
          </p>
        </div>
        <Link
          href="/exportaciones/nueva"
          className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
        >
          Nueva exportación
        </Link>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <span className="block text-gray-600 mb-1">Tipo</span>
          <select
            className="border rounded px-2 py-1"
            value={tipo}
            onChange={(e) => {
              setTipo(e.target.value as TipoExportacion | "");
              setPage(1);
            }}
          >
            <option value="">Todos</option>
            <option value="INTEGRAL">Integral</option>
            <option value="SII">SII</option>
          </select>
        </label>
        <label className="text-sm">
          <span className="block text-gray-600 mb-1">Estado</span>
          <select
            className="border rounded px-2 py-1"
            value={estado}
            onChange={(e) => {
              setEstado(e.target.value as EstadoExportacion | "");
              setPage(1);
            }}
          >
            <option value="">Todos</option>
            <option value="lista">Lista</option>
            <option value="en_proceso">En proceso</option>
            <option value="fallida">Fallida</option>
          </select>
        </label>
        <span className="text-sm text-gray-500">{total} exportación(es)</span>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {cargando ? (
        <p className="text-sm text-gray-500">Cargando exportaciones…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-gray-500">
          Todavía no hay exportaciones. Crea la primera desde «Nueva exportación».
        </p>
      ) : (
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b text-left text-gray-500">
              <th className="py-2 pr-3">Nº</th>
              <th className="py-2 pr-3">Tipo</th>
              <th className="py-2 pr-3">Estado</th>
              <th className="py-2 pr-3">Ejercicios</th>
              <th className="py-2 pr-3">Bloques</th>
              <th className="py-2 pr-3">Tamaño</th>
              <th className="py-2 pr-3">Huella</th>
              <th className="py-2">Detalle</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.exportacion_id} className="border-b hover:bg-gray-50">
                <td className="py-1.5 pr-3">
                  {item.anio_creacion}/{item.numero_exportacion}
                </td>
                <td className="py-1.5 pr-3">{item.tipo}</td>
                <td className="py-1.5 pr-3">
                  <span
                    className={`rounded px-2 py-0.5 text-xs ${
                      item.estado === "lista"
                        ? "bg-green-100 text-green-800"
                        : item.estado === "fallida"
                          ? "bg-red-100 text-red-800"
                          : "bg-gray-100 text-gray-700"
                    }`}
                  >
                    {ETIQUETA_ESTADO[item.estado]}
                  </span>
                </td>
                <td className="py-1.5 pr-3 font-mono text-xs">
                  {item.ejercicio_desde ?? "—"} → {item.ejercicio_hasta ?? "—"}
                </td>
                <td className="py-1.5 pr-3">{item.n_bloques}</td>
                <td className="py-1.5 pr-3">{formatearBytes(item.tamano_bytes)}</td>
                <td className="py-1.5 pr-3 font-mono text-xs">
                  {item.sha256 ? `${item.sha256.slice(0, 12)}…` : "—"}
                </td>
                <td className="py-1.5">
                  <Link
                    className="text-blue-600 underline"
                    href={`/exportaciones/${item.exportacion_id}`}
                  >
                    Ver detalle
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {paginas > 1 && (
        <div className="flex items-center gap-2 text-sm">
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="rounded border px-3 py-1 disabled:opacity-50"
          >
            Anterior
          </button>
          <span>
            Página {page} de {paginas}
          </span>
          <button
            type="button"
            onClick={() => setPage((p) => Math.min(paginas, p + 1))}
            disabled={page >= paginas}
            className="rounded border px-3 py-1 disabled:opacity-50"
          >
            Siguiente
          </button>
        </div>
      )}
    </main>
  );
}
