"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import {
  ApiError,
  importarCatalogo,
  type ResultadoImport,
} from "@/components/catalog/api";

export default function ImportarCatalogoPage() {
  const router = useRouter();
  const [archivo, setArchivo] = useState<File | null>(null);
  const [codigo, setCodigo] = useState("");
  const [fechaInicio, setFechaInicio] = useState("");
  const [fechaFin, setFechaFin] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resultado, setResultado] = useState<ResultadoImport | null>(null);

  async function enviar(evento: React.FormEvent) {
    evento.preventDefault();
    if (!archivo || !codigo || !fechaInicio) {
      setError("Fichero, código de versión y fecha de inicio son obligatorios.");
      return;
    }
    setEnviando(true);
    setError(null);
    setResultado(null);
    try {
      const res = await importarCatalogo(
        archivo,
        codigo,
        fechaInicio,
        fechaFin || undefined
      );
      setResultado(res);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error de conexión");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <main className="p-6 max-w-3xl mx-auto space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Importar normativa</h1>
        <Link className="text-sm text-blue-600 underline" href="/catalogo">
          Volver al catálogo
        </Link>
      </div>

      <p className="text-sm text-gray-600">
        CSV con cabecera{" "}
        <code className="bg-gray-100 px-1">
          operacion,codigo,nombre,padre_codigo,destino_codigo
        </code>{" "}
        (operaciones: alta, renombrado, baja) o JSON de importación. La versión
        se crea en borrador y deberá activarse tras revisar los pendientes de
        mapeo.
      </p>

      <form onSubmit={enviar} className="rounded border p-4 space-y-3">
        <div className="space-y-1">
          <label className="block text-sm" htmlFor="fichero">
            Fichero
          </label>
          <input
            id="fichero"
            type="file"
            accept=".csv,.json,text/csv,application/json"
            onChange={(evento) => setArchivo(evento.target.files?.[0] ?? null)}
            className="text-sm"
          />
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div className="space-y-1">
            <label className="block text-sm" htmlFor="codigo">
              Código de versión
            </label>
            <input
              id="codigo"
              type="text"
              value={codigo}
              onChange={(evento) => setCodigo(evento.target.value)}
              className="w-full border rounded px-2 py-1 text-sm"
              placeholder="PGC-2026-import"
            />
          </div>
          <div className="space-y-1">
            <label className="block text-sm" htmlFor="inicio">
              Vigente desde
            </label>
            <input
              id="inicio"
              type="date"
              value={fechaInicio}
              onChange={(evento) => setFechaInicio(evento.target.value)}
              className="w-full border rounded px-2 py-1 text-sm"
            />
          </div>
          <div className="space-y-1">
            <label className="block text-sm" htmlFor="fin">
              Vigente hasta (opcional)
            </label>
            <input
              id="fin"
              type="date"
              value={fechaFin}
              onChange={(evento) => setFechaFin(evento.target.value)}
              className="w-full border rounded px-2 py-1 text-sm"
            />
          </div>
        </div>
        <button
          type="submit"
          disabled={enviando}
          className="rounded bg-blue-600 px-4 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {enviando ? "Importando…" : "Importar"}
        </button>
      </form>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {resultado && (
        <section className="rounded border p-4 space-y-3">
          <h2 className="font-medium">Resultado de la importación</h2>
          <ul className="grid grid-cols-4 gap-2 text-sm">
            <li>Nuevas: {resultado.nuevas}</li>
            <li>Renombradas: {resultado.renombradas}</li>
            <li>Suprimidas: {resultado.suprimidas}</li>
            <li>Mapeos: {resultado.mapeos}</li>
          </ul>

          {resultado.pendientes_mapeo.length > 0 ? (
            <div className="rounded border border-amber-300 bg-amber-50 p-3 space-y-2">
              <p className="text-sm font-medium text-amber-900">
                Pendientes de mapeo: la activación quedará bloqueada hasta
                resolverlos.
              </p>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-amber-800">
                    <th className="py-1 pr-3">Cuenta</th>
                    <th className="py-1">Motivo</th>
                  </tr>
                </thead>
                <tbody>
                  {resultado.pendientes_mapeo.map((pendiente) => (
                    <tr key={pendiente.codigo} className="border-t border-amber-200">
                      <td className="py-1 pr-3 font-mono">{pendiente.codigo}</td>
                      <td className="py-1">{pendiente.motivo}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-emerald-700">
              Sin pendientes de mapeo: la versión puede activarse.
            </p>
          )}

          <div className="flex gap-3 text-sm">
            <button
              type="button"
              className="text-blue-600 underline"
              onClick={() => router.push(`/catalogo/${resultado.version_id}`)}
            >
              Ver la versión importada
            </button>
            <button
              type="button"
              className="text-blue-600 underline"
              onClick={() => {
                setResultado(null);
                setArchivo(null);
                setCodigo("");
              }}
            >
              Importar otra
            </button>
          </div>
        </section>
      )}
    </main>
  );
}
