"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  ApiError,
  listarVersiones,
  type EstadoVersion,
  type VersionResumen,
} from "@/components/catalog/api";

const ETIQUETAS_ESTADO: Record<EstadoVersion, string> = {
  borrador: "Borrador",
  vigente: "Vigente",
  anulada: "Anulada",
};

const CLASES_ESTADO: Record<EstadoVersion, string> = {
  borrador: "bg-amber-100 text-amber-800",
  vigente: "bg-emerald-100 text-emerald-800",
  anulada: "bg-gray-200 text-gray-600",
};

export default function CatalogoPage() {
  const [items, setItems] = useState<VersionResumen[]>([]);
  const [total, setTotal] = useState(0);
  const [estado, setEstado] = useState("");
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function recargar(filtro: string) {
    setCargando(true);
    setError(null);
    try {
      const datos = await listarVersiones(filtro ? { estado: filtro } : {});
      setItems(datos.items);
      setTotal(datos.total);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error de conexión");
    } finally {
      setCargando(false);
    }
  }

  useEffect(() => {
    void recargar(estado);
  }, [estado]);

  return (
    <main className="p-6 max-w-5xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Catálogo versionado</h1>
        <div className="flex items-center gap-3">
          <label className="text-sm text-gray-600" htmlFor="estado">
            Estado
          </label>
          <select
            id="estado"
            className="border rounded px-2 py-1 text-sm"
            value={estado}
            onChange={(evento) => setEstado(evento.target.value)}
          >
            <option value="">Todos</option>
            <option value="borrador">Borrador</option>
            <option value="vigente">Vigente</option>
            <option value="anulada">Anulada</option>
          </select>
          <Link
            className="text-sm text-blue-600 underline"
            href="/catalogo/importar"
          >
            Importar normativa
          </Link>
          <Link
            className="text-sm text-blue-600 underline"
            href="/catalogo/reclasificar"
          >
            Reclasificar saldos
          </Link>
        </div>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {cargando ? (
        <p className="text-sm text-gray-500">Cargando…</p>
      ) : (
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b text-left text-gray-500">
              <th className="py-2 pr-3">Nº</th>
              <th className="py-2 pr-3">Código</th>
              <th className="py-2 pr-3">Vigencia</th>
              <th className="py-2 pr-3">Estado</th>
              <th className="py-2 pr-3">Migración</th>
              <th className="py-2"> </th>
            </tr>
          </thead>
          <tbody>
            {items.map((version) => (
              <tr key={version.id} className="border-b hover:bg-gray-50">
                <td className="py-2 pr-3 font-mono">{version.numero_version}</td>
                <td className="py-2 pr-3 font-medium">{version.codigo}</td>
                <td className="py-2 pr-3">
                  {version.fecha_inicio}
                  {" → "}
                  {version.fecha_fin ?? "…"}
                </td>
                <td className="py-2 pr-3">
                  <span
                    className={`rounded px-2 py-0.5 text-xs ${CLASES_ESTADO[version.estado]}`}
                  >
                    {ETIQUETAS_ESTADO[version.estado]}
                  </span>
                </td>
                <td className="py-2 pr-3">{version.es_migracion ? "sí" : "no"}</td>
                <td className="py-2 text-right">
                  <Link
                    className="text-blue-600 underline"
                    href={`/catalogo/${version.id}`}
                  >
                    detalle
                  </Link>
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={6} className="py-4 text-gray-500">
                  No hay versiones con ese filtro.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}

      <p className="text-xs text-gray-500">{total} versión(es)</p>
    </main>
  );
}
