"use client";

import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  Documento,
  ListadoDocumentos,
  TIPOS_DOCUMENTO,
  TipoDocumento,
  adjuntarDocumentos,
  darDeBajaDocumento,
  descargarDocumento,
  listarDocumentosAsiento,
} from "@/components/documentos/api";
import { VisorDocumento } from "@/components/documentos/VisorDocumento";

interface Props {
  asientoId: string;
  estadoAsiento: string;
}

const ACCEPT = ".pdf,.jpg,.jpeg,.png,.tif,.tiff";

/** Formatea bytes sin depender del locale del navegador. */
function tamano(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function DocumentosAsiento({ asientoId, estadoAsiento }: Props) {
  const [listado, setListado] = useState<ListadoDocumentos | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [incluirBajas, setIncluirBajas] = useState(false);
  const [tipo, setTipo] = useState<TipoDocumento>("factura");
  const [descripcion, setDescripcion] = useState("");
  const [importe, setImporte] = useState("");
  const [motivo, setMotivo] = useState("");
  const [bajaEnCurso, setBajaEnCurso] = useState<string | null>(null);
  const [visor, setVisor] = useState<Documento | null>(null);

  const cargar = useCallback(async () => {
    try {
      setListado(await listarDocumentosAsiento(asientoId, incluirBajas));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error de conexión");
    }
  }, [asientoId, incluirBajas]);

  // Un solo efecto: la primera pintura y el cambio de filtro entran por el
  // mismo camino, porque `cargar` ya depende de `incluirBajas`.
  useEffect(() => {
    void cargar();
  }, [cargar]);

  async function subir(seleccion: FileList | null) {
    if (!seleccion || seleccion.length === 0) return;
    setEnviando(true);
    setError(null);
    setAviso(null);
    try {
      const resultado = await adjuntarDocumentos(
        asientoId,
        Array.from(seleccion),
        tipo,
        descripcion || undefined,
        importe || undefined
      );
      const rechazados = resultado.rechazados;
      // FR-018: los aceptados se conservan y el aviso explica los rechazos.
      setAviso(
        rechazados.length > 0
          ? `${resultado.aceptados.length} adjuntado(s). Rechazados: ` +
              rechazados.map((r) => `${r.nombre} (${r.detail})`).join("; ")
          : `${resultado.aceptados.length} documento(s) adjuntado(s).`
      );
      setDescripcion("");
      setImporte("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error de conexión");
    } finally {
      setEnviando(false);
      // Un `.bak` que se rechaza no rompe el input: se vacia siempre, para
      // poder volver a elegir el mismo fichero.
      await cargar();
    }
  }

  async function darDeBaja(documento: Documento) {
    const texto = motivo.trim();
    if (!texto) {
      setError("El motivo de la baja es obligatorio");
      return;
    }
    if (!window.confirm(`¿Dar de baja "${documento.nombre_original}"?`)) return;
    setBajaEnCurso(documento.id);
    setError(null);
    try {
      await darDeBajaDocumento(documento.id, texto);
      setMotivo("");
      setAviso("Documento dado de baja. Su contenido y su huella se conservan.");
      await cargar();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error de conexión");
    } finally {
      setBajaEnCurso(null);
    }
  }

  const items = listado?.items ?? [];
  const activos = items.filter((d) => d.estado === "activo");
  const bajas = items.filter((d) => d.estado === "dado_de_baja");
  // FR-010: la baja solo es posible sobre un asiento en borrador. El boton no
  // se pinta en un asiento contabilizado, y el backend lo rechaza igual (409).
  const bajaPermitida = estadoAsiento === "DRAFT";

  return (
    <section className="mt-8 border-t pt-4">
      <h2 className="text-lg font-semibold mb-2">
        Documentos adjuntos ({activos.length})
      </h2>
      <p className="text-sm text-gray-600 mb-4">
        Los adjuntos son <strong>opcionales</strong>: el asiento es válido sin
        ellos y su cuadre no depende de que exista ninguno. Adjuntar aporta
        evidencia, no habilita el apunte.
      </p>

      {error && <p className="text-red-600 mb-2">{error}</p>}
      {aviso && <p className="text-green-700 mb-2">{aviso}</p>}

      <div className="flex flex-wrap gap-3 items-end mb-4">
        <label className="text-sm">
          <span className="block">Ficheros (PDF o imagen)</span>
          <input
            type="file"
            multiple
            accept={ACCEPT}
            disabled={enviando}
            onChange={(e) => {
              const seleccion = e.target.files;
              e.target.value = "";
              void subir(seleccion);
            }}
            className="text-sm"
          />
        </label>
        <label className="text-sm">
          <span className="block">Tipo</span>
          <select
            value={tipo}
            onChange={(e) => setTipo(e.target.value as TipoDocumento)}
            className="border rounded px-2 py-1 text-sm"
          >
            {TIPOS_DOCUMENTO.map((t) => (
              <option key={t.valor} value={t.valor}>
                {t.etiqueta}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <span className="block">Descripción</span>
          <input
            type="text"
            value={descripcion}
            maxLength={500}
            onChange={(e) => setDescripcion(e.target.value)}
            className="border rounded px-2 py-1 text-sm"
          />
        </label>
        <label className="text-sm">
          <span className="block">Importe informativo</span>
          <input
            type="text"
            inputMode="decimal"
            placeholder="1210.0000"
            value={importe}
            onChange={(e) => setImporte(e.target.value)}
            className="border rounded px-2 py-1 text-sm w-32"
          />
        </label>
      </div>

      {activos.length === 0 ? (
        <p className="text-sm text-gray-500">
          Este asiento todavía no tiene documentos adjuntos. Es correcto: puede
          contabilizarse, anularse y exportarse sin ninguno.
        </p>
      ) : (
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b">
              <th className="text-left p-2">Nombre</th>
              <th className="text-left p-2">Tipo</th>
              <th className="text-right p-2">Tamaño</th>
              <th className="text-right p-2">Págs.</th>
              <th className="text-left p-2">Huella</th>
              <th className="text-left p-2">Acciones</th>
            </tr>
          </thead>
          <tbody>
            {activos.map((documento) => (
              <tr key={documento.id} className="border-b">
                <td className="p-2">
                  {documento.nombre_original}
                  {documento.descripcion && (
                    <span className="block text-xs text-gray-500">
                      {documento.descripcion}
                    </span>
                  )}
                  {documento.importe_informativo && (
                    <span className="block text-xs text-gray-500">
                      Importe informativo: {documento.importe_informativo} (no
                      altera el asiento)
                    </span>
                  )}
                </td>
                <td className="p-2">{documento.tipo_documento}</td>
                <td className="text-right p-2 font-mono">
                  {tamano(documento.size_bytes)}
                </td>
                <td className="text-right p-2 font-mono">
                  {documento.num_paginas ?? "—"}
                </td>
                <td className="p-2 font-mono text-xs">
                  {documento.sha256.slice(0, 12)}…
                </td>
                <td className="p-2">
                  <div className="flex gap-2">
                    <button
                      onClick={() => setVisor(documento)}
                      className="border rounded px-2 py-1 text-xs"
                    >
                      Ver
                    </button>
                    <button
                      onClick={() =>
                        void descargarDocumento(
                          documento.id,
                          documento.nombre_original
                        )
                      }
                      className="border rounded px-2 py-1 text-xs"
                    >
                      Descargar
                    </button>
                    {bajaPermitida && (
                      <button
                        disabled={bajaEnCurso === documento.id}
                        onClick={() => void darDeBaja(documento)}
                        className="border border-red-300 text-red-700 rounded px-2 py-1 text-xs"
                      >
                        Dar de baja
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {bajaPermitida && (
        <label className="block text-sm mt-4 max-w-md">
          <span className="block">Motivo de la baja (obligatorio)</span>
          <input
            type="text"
            maxLength={500}
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            className="border rounded px-2 py-1 text-sm w-full"
          />
        </label>
      )}

      {bajas.length > 0 && (
        <div className="mt-4">
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={incluirBajas}
              onChange={(e) => setIncluirBajas(e.target.checked)}
            />
            Mostrar documentos dados de baja ({bajas.length})
          </label>
          <ul className="text-sm text-gray-600 mt-2 space-y-1">
            {bajas.map((documento) => (
              <li key={documento.id}>
                {documento.nombre_original} — dado de baja por{" "}
                {documento.baja_usuario} el {documento.baja_at?.slice(0, 19)}:{" "}
                {documento.baja_motivo}. El contenido y su huella se conservan.
              </li>
            ))}
          </ul>
        </div>
      )}

      {visor && (
        <VisorDocumento documento={visor} onClose={() => setVisor(null)} />
      )}
    </section>
  );
}
