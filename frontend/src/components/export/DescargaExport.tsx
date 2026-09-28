"use client";

import { useState } from "react";

import {
  ApiError,
  descargarExportacion,
  formatearBytes,
  type Exportacion,
} from "./api";

/**
 * Boton de descarga del ZIP (plan.md: `components/export/DescargaExport.tsx`).
 *
 * La descarga va autenticada (JWT + empresa activa), por eso usa el blob del
 * cliente HTTP y no un `<a href>` plano. Solo habilita si la exportacion esta
 * en estado `lista`.
 */
export default function DescargaExport({
  exportacion,
  onMensaje,
}: {
  exportacion: Exportacion;
  onMensaje?: (mensaje: string | null) => void;
}) {
  const [descargando, setDescargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const disponible = exportacion.estado === "lista";

  async function descargar() {
    setDescargando(true);
    setError(null);
    onMensaje?.(null);
    try {
      await descargarExportacion(exportacion.exportacion_id);
      onMensaje?.(
        `Descargado ${exportacion.nombre_fichero ?? exportacion.exportacion_id} (${formatearBytes(
          exportacion.tamano_bytes
        )}).`
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "No se pudo descargar la exportación");
    } finally {
      setDescargando(false);
    }
  }

  return (
    <div className="space-y-1">
      <button
        type="button"
        onClick={() => void descargar()}
        disabled={!disponible || descargando}
        className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {descargando ? "Descargando…" : "Descargar ZIP"}
      </button>
      {!disponible && (
        <p className="text-xs text-amber-700">
          La exportación está en estado «{exportacion.estado}»: no se puede descargar.
        </p>
      )}
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}
