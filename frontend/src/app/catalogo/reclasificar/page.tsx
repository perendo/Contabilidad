"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  ApiError,
  confirmarReclasificacion,
  listarVersiones,
  previewReclasificacion,
  type ItemReclasif,
  type PreviewReclasif,
  type ResultadoConfirm,
  type VersionResumen,
} from "@/components/catalog/api";

export default function ReclasificarCatalogoPage() {
  const [versiones, setVersiones] = useState<VersionResumen[]>([]);
  const [versionId, setVersionId] = useState("");
  const [ejercicio, setEjercicio] = useState("2025");
  const [preview, setPreview] = useState<PreviewReclasif | null>(null);
  const [resultado, setResultado] = useState<ResultadoConfirm | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const datos = await listarVersiones({ page_size: 100 });
        setVersiones(datos.items);
        if (datos.items.length > 0) setVersionId(datos.items[0].id);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "Error de conexión");
      }
    })();
  }, []);

  function mensaje(e: unknown): string {
    return e instanceof ApiError ? e.message : "Error de conexión";
  }

  async function previsualizar() {
    if (!versionId || !ejercicio) return;
    setOcupado(true);
    setError(null);
    setResultado(null);
    setPreview(null);
    try {
      setPreview(await previewReclasificacion(versionId, Number(ejercicio)));
    } catch (e) {
      setError(mensaje(e));
    } finally {
      setOcupado(false);
    }
  }

  async function confirmar() {
    if (!preview) return;
    const ok = window.confirm(
      `¿Confirmar la reclasificación de ${preview.total_importe} en el ejercicio ${ejercicio}?\n` +
        "Se generarán asientos ADJUSTMENT; los asientos históricos no se modifican."
    );
    if (!ok) return;
    setOcupado(true);
    setError(null);
    try {
      const items: ItemReclasif[] = preview.items;
      setResultado(
        await confirmarReclasificacion(versionId, Number(ejercicio), items)
      );
      setPreview(null);
    } catch (e) {
      setError(mensaje(e));
    } finally {
      setOcupado(false);
    }
  }

  return (
    <main className="p-6 max-w-4xl mx-auto space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Reclasificación de saldos</h1>
        <Link className="text-sm text-blue-600 underline" href="/catalogo">
          Volver al catálogo
        </Link>
      </div>

      <section className="rounded border p-4 grid grid-cols-3 gap-3 items-end">
        <div className="space-y-1">
          <label className="block text-sm" htmlFor="version">
            Versión destino
          </label>
          <select
            id="version"
            className="w-full border rounded px-2 py-1 text-sm"
            value={versionId}
            onChange={(evento) => setVersionId(evento.target.value)}
          >
            {versiones.map((version) => (
              <option key={version.id} value={version.id}>
                v{version.numero_version} · {version.codigo} ({version.estado})
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <label className="block text-sm" htmlFor="ejercicio">
            Ejercicio con saldos
          </label>
          <input
            id="ejercicio"
            type="number"
            min={2000}
            max={2100}
            className="w-full border rounded px-2 py-1 text-sm"
            value={ejercicio}
            onChange={(evento) => setEjercicio(evento.target.value)}
          />
        </div>
        <button
          type="button"
          onClick={() => void previsualizar()}
          disabled={ocupado || !versionId}
          className="rounded bg-blue-600 px-4 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
        >
          Previsualizar
        </button>
      </section>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {preview && (
        <section className="rounded border p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-medium">
              Traslados propuestos ({preview.items.length})
            </h2>
            <span className="text-sm font-mono">{preview.total_importe}</span>
          </div>
          {preview.items.length === 0 ? (
            <p className="text-sm text-gray-500">
              No hay saldos reclasificables en ese ejercicio.
            </p>
          ) : (
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b text-left text-gray-500">
                  <th className="py-2 pr-3">Origen</th>
                  <th className="py-2 pr-3">Destino</th>
                  <th className="py-2 text-right">Importe</th>
                </tr>
              </thead>
              <tbody>
                {preview.items.map((item) => (
                  <tr key={item.cuenta_origen_id} className="border-b">
                    <td className="py-1.5 pr-3 font-mono">{item.codigo_origen}</td>
                    <td className="py-1.5 pr-3 font-mono">{item.codigo_destino}</td>
                    <td className="py-1.5 text-right font-mono">{item.importe}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <button
            type="button"
            onClick={() => void confirmar()}
            disabled={ocupado || preview.items.length === 0}
            className="rounded bg-emerald-600 px-4 py-1.5 text-sm text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            Confirmar reclasificación
          </button>
        </section>
      )}

      {resultado && (
        <section className="rounded border p-4 space-y-3">
          <h2 className="font-medium">Reclasificación contabilizada</h2>
          <ul className="text-sm space-y-1">
            <li>Reclasificaciones: {resultado.reclasificaciones}</li>
            <li>Importe total: {resultado.total_importe}</li>
          </ul>
          {resultado.asientos.length > 0 && (
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b text-left text-gray-500">
                  <th className="py-2 pr-3">Asiento</th>
                  <th className="py-2 pr-3">Número</th>
                  <th className="py-2">Cuadre</th>
                </tr>
              </thead>
              <tbody>
                {resultado.asientos.map((asiento) => (
                  <tr key={asiento.asiento_id} className="border-b">
                    <td className="py-1.5 pr-3">
                      <Link
                        className="text-blue-600 underline font-mono"
                        href={`/asientos/${asiento.asiento_id}`}
                      >
                        ver asiento
                      </Link>
                    </td>
                    <td className="py-1.5 pr-3">{asiento.numero_asiento}</td>
                    <td className="py-1.5">
                      {asiento.cuadre ? (
                        <span className="rounded bg-emerald-100 text-emerald-800 px-2 py-0.5 text-xs">
                          cuadrado
                        </span>
                      ) : (
                        <span className="rounded bg-red-100 text-red-800 px-2 py-0.5 text-xs">
                          descuadrado
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}
    </main>
  );
}
