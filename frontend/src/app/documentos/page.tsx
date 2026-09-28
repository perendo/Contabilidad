"use client";

import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  EstadoDocumento,
  FiltrosDocumentos,
  ItemGlobalDocumento,
  TIPOS_DOCUMENTO,
  TipoDocumento,
  descargarDocumento,
  listarDocumentos,
} from "@/components/documentos/api";
import { VisorDocumento } from "@/components/documentos/VisorDocumento";

function tamano(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DocumentosPage() {
  const [items, setItems] = useState<ItemGlobalDocumento[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [visor, setVisor] = useState<ItemGlobalDocumento | null>(null);

  const [ejercicio, setEjercicio] = useState("");
  const [tipo, setTipo] = useState<TipoDocumento | "">("");
  const [estado, setEstado] = useState<EstadoDocumento | "">("");
  const [q, setQ] = useState("");
  const [incluirBajas, setIncluirBajas] = useState(true);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    const filtros: FiltrosDocumentos = { page, page_size: 20 };
    if (ejercicio) filtros.ejercicio = Number(ejercicio);
    if (tipo) filtros.tipo_documento = tipo;
    if (estado) filtros.estado = estado;
    if (q.trim()) filtros.q = q.trim();
    if (!incluirBajas) filtros.incluir_bajas = false;
    try {
      const respuesta = await listarDocumentos(filtros);
      setItems(respuesta.items);
      setTotal(respuesta.total);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error de conexión");
    } finally {
      setCargando(false);
    }
  }, [ejercicio, tipo, estado, q, incluirBajas, page]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  function reiniciar() {
    setEjercicio("");
    setTipo("");
    setEstado("");
    setQ("");
    setIncluirBajas(true);
    setPage(1);
    setAviso("Filtros reiniciados");
  }

  const paginas = Math.max(1, Math.ceil(total / 20));

  return (
    <main className="p-6 max-w-6xl mx-auto">
      <h1 className="text-xl font-semibold mb-2">Documentos del diario</h1>
      <p className="text-sm text-gray-600 mb-4">
        Evidencia documental anexa a los asientos. Los documentos son
        <strong> opcionales</strong>: su ausencia no invalida ningún apunte.
      </p>

      <div className="flex flex-wrap gap-3 items-end mb-4">
        <label className="text-sm">
          <span className="block">Ejercicio del asiento</span>
          <input
            type="number"
            value={ejercicio}
            onChange={(e) => {
              setEjercicio(e.target.value);
              setPage(1);
            }}
            className="border rounded px-2 py-1 w-28"
          />
        </label>
        <label className="text-sm">
          <span className="block">Tipo</span>
          <select
            value={tipo}
            onChange={(e) => {
              setTipo(e.target.value as TipoDocumento | "");
              setPage(1);
            }}
            className="border rounded px-2 py-1"
          >
            <option value="">Todos</option>
            {TIPOS_DOCUMENTO.map((t) => (
              <option key={t.valor} value={t.valor}>
                {t.etiqueta}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <span className="block">Estado</span>
          <select
            value={estado}
            onChange={(e) => {
              setEstado(e.target.value as EstadoDocumento | "");
              setPage(1);
            }}
            className="border rounded px-2 py-1"
          >
            <option value="">Todos</option>
            <option value="activo">Activo</option>
            <option value="dado_de_baja">Dado de baja</option>
          </select>
        </label>
        <label className="text-sm">
          <span className="block">Buscar</span>
          <input
            type="text"
            maxLength={200}
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
            placeholder="nombre o descripción"
            className="border rounded px-2 py-1"
          />
        </label>
        <label className="text-sm flex items-center gap-1">
          <input
            type="checkbox"
            checked={incluirBajas}
            onChange={(e) => setIncluirBajas(e.target.checked)}
          />
          Incluir dadas de baja
        </label>
        <button
          onClick={reiniciar}
          className="text-sm border rounded px-3 py-1"
        >
          Limpiar
        </button>
      </div>

      {cargando && <p className="text-sm text-gray-500">Cargando…</p>}
      {error && <p className="text-red-600 text-sm">{error}</p>}
      {aviso && <p className="text-green-700 text-sm">{aviso}</p>}
      {!cargando && !error && items.length === 0 && (
        <p className="text-sm text-gray-500">
          No hay documentos que cumplan el filtro.
        </p>
      )}

      {items.length > 0 && (
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b">
              <th className="text-left p-2">Nombre</th>
              <th className="text-left p-2">Tipo</th>
              <th className="text-right p-2">Tamaño</th>
              <th className="text-left p-2">Huella</th>
              <th className="text-left p-2">Fecha</th>
              <th className="text-left p-2">Asiento</th>
              <th className="text-left p-2">Acciones</th>
            </tr>
          </thead>
          <tbody>
            {items.map((documento) => (
              <tr
                key={documento.id}
                className={documento.estado === "dado_de_baja" ? "opacity-60" : ""}
              >
                <td className="p-2">
                  {documento.nombre_original}
                  {documento.estado === "dado_de_baja" && (
                    <span className="block text-xs text-red-700">
                      Dado de baja: {documento.baja_motivo}
                    </span>
                  )}
                </td>
                <td className="p-2">{documento.tipo_documento}</td>
                <td className="text-right p-2 font-mono">
                  {tamano(documento.size_bytes)}
                </td>
                <td className="p-2 font-mono text-xs">
                  {documento.sha256.slice(0, 12)}…
                </td>
                <td className="p-2 text-xs">
                  {documento.created_at.slice(0, 19)}
                </td>
                <td className="p-2 text-xs">
                  {documento.journal_entry && (
                    <>
                      Nº {documento.journal_entry.numero ?? "borrador"} ·{" "}
                      {documento.journal_entry.fecha} ·{" "}
                      {documento.journal_entry.ejercicio}
                    </>
                  )}
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
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="flex items-center gap-3 mt-4 text-sm">
        <span>
          {total} documento(s) · página {page} de {paginas}
        </span>
        <button
          disabled={page <= 1}
          onClick={() => setPage((p) => p - 1)}
          className="border rounded px-2 py-1 disabled:opacity-40"
        >
          Anterior
        </button>
        <button
          disabled={page >= paginas}
          onClick={() => setPage((p) => p + 1)}
          className="border rounded px-2 py-1 disabled:opacity-40"
        >
          Siguiente
        </button>
      </div>

      {visor && (
        <VisorDocumento documento={visor} onClose={() => setVisor(null)} />
      )}
    </main>
  );
}
