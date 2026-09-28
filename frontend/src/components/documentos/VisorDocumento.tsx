"use client";

import { useEffect, useState } from "react";

import {
  ApiError,
  Documento,
  descargarDocumento,
  obtenerBlobDocumento,
} from "@/components/documentos/api";

interface Props {
  documento: Documento;
  onClose: () => void;
}

/** research D12: la previsualizacion usa una URL de objeto creada en el cliente
 * a partir del blob **autenticado**, nunca una URL publica: asi el contenido de
 * un tenant no queda expuesto a otro. `<iframe>` para PDF (visor nativo del
 * navegador) y `<img>` para imagen. */
export function VisorDocumento({ documento, onClose }: Props) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let objectUrl: string | null = null;
    let vivo = true;

    obtenerBlobDocumento(documento.id)
      .then((blob) => {
        if (!vivo) return;
        objectUrl = window.URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch((e) => {
        if (!vivo) return;
        setError(e instanceof ApiError ? e.message : "Error al cargar el documento");
      });

    // Se revoca la URL al cerrar o al cambiar de documento: una URL de objeto
    // sin revocar retiene el binario en memoria del navegador.
    return () => {
      vivo = false;
      if (objectUrl) window.URL.revokeObjectURL(objectUrl);
    };
  }, [documento.id]);

  const esImagen = documento.content_type.startsWith("image/");

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center p-6 z-50"
      role="dialog"
      aria-modal="true"
      aria-label={`Documento ${documento.nombre_original}`}
    >
      <div className="bg-white rounded max-w-4xl w-full max-h-full flex flex-col">
        <header className="flex items-center justify-between p-3 border-b">
          <div>
            <p className="font-medium">{documento.nombre_original}</p>
            <p className="text-xs text-gray-500">
              {documento.content_type} ·{" "}
              <span className="font-mono">{documento.sha256.slice(0, 16)}…</span>
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() =>
                void descargarDocumento(documento.id, documento.nombre_original)
              }
              className="border rounded px-2 py-1 text-sm"
            >
              Descargar
            </button>
            <button
              onClick={onClose}
              className="border rounded px-2 py-1 text-sm"
            >
              Cerrar
            </button>
          </div>
        </header>

        <div className="p-3 overflow-auto flex-1 min-h-[16rem]">
          {error && <p className="text-red-600 text-sm">{error}</p>}
          {!error && !url && <p className="text-gray-500 text-sm">Cargando…</p>}
          {url && esImagen && (
            // `next/image` no sirve aqui: la fuente es una URL de objeto local
            // con dimensiones desconocidas, que es justo lo que no puede medir.
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={url}
              alt={documento.nombre_original}
              className="max-w-full mx-auto"
            />
          )}
          {url && !esImagen && (
            <iframe
              src={url}
              title={documento.nombre_original}
              className="w-full h-[60vh] border"
            />
          )}
        </div>

        <footer className="p-3 border-t text-xs text-gray-500">
          Si el navegador no puede previsualizar el PDF, use la descarga: el
          contenido es el mismo y su huella la verifica el servidor.
        </footer>
      </div>
    </div>
  );
}
