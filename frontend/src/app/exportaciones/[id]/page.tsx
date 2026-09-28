"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import DescargaExport from "@/components/export/DescargaExport";
import {
  ApiError,
  ETIQUETA_ESTADO,
  formatearBytes,
  obtenerBloqueSii,
  obtenerExportacion,
  verificarExportacion,
  type BloqueSii,
  type ConfigSii,
  type DetalleExportacion,
  type Verificacion,
} from "@/components/export/api";
import ManifiestoEstado from "@/components/export/ManifiestoEstado";

/** T026: detalle con el manifiesto de bloques, descarga y verificacion. */
export default function DetalleExportacionPage() {
  const params = useParams<{ id: string }>();
  const exportacionId = params.id;
  const [detalle, setDetalle] = useState<DetalleExportacion | null>(null);
  const [verificacion, setVerificacion] = useState<Verificacion | null>(null);
  const [config, setConfig] = useState<ConfigSii | null>(null);
  const [sii, setSii] = useState<BloqueSii[] | null>(null);
  const [cargando, setCargando] = useState(true);
  const [verificando, setVerificando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mensaje, setMensaje] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      setDetalle(await obtenerExportacion(exportacionId));
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "No se pudo cargar la exportación"
      );
    } finally {
      setCargando(false);
    }
  }, [exportacionId]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  async function verificar() {
    setVerificando(true);
    setError(null);
    try {
      setVerificacion(await verificarExportacion(exportacionId));
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "No se pudo verificar la integridad"
      );
    } finally {
      setVerificando(false);
    }
  }

  async function cargarSii() {
    setError(null);
    try {
      const respuesta = await obtenerBloqueSii(exportacionId);
      setConfig(respuesta.config);
      setSii(respuesta.bloques_sii);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "No se pudo leer el bloque SII");
    }
  }

  if (cargando) {
    return (
      <main className="p-6 max-w-5xl mx-auto">
        <p className="text-sm text-gray-500">Cargando exportación…</p>
      </main>
    );
  }

  if (!detalle) {
    return (
      <main className="p-6 max-w-5xl mx-auto space-y-2">
        <p className="text-sm text-red-600">{error ?? "Exportación no encontrada"}</p>
        <Link className="text-blue-600 underline" href="/exportaciones">
          Volver al listado
        </Link>
      </main>
    );
  }

  const manifiesto = detalle.manifiesto;
  const registros = detalle.n_bloques;

  return (
    <main className="p-6 max-w-5xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">
            Exportación {detalle.anio_creacion}/{detalle.numero_exportacion}
          </h1>
          <p className="text-sm text-gray-500">
            {detalle.tipo} · {ETIQUETA_ESTADO[detalle.estado]} · {registros} bloques ·{" "}
            {formatearBytes(detalle.tamano_bytes)}
          </p>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <Link className="text-blue-600 underline" href="/exportaciones">
            Exportaciones
          </Link>
          <Link className="text-blue-600 underline" href="/exportaciones/nueva">
            Nueva
          </Link>
        </div>
      </div>

      {detalle.mensaje_error && (
        <p className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800">
          {detalle.mensaje_error}
        </p>
      )}

      <section className="rounded border bg-white p-4 text-sm space-y-2">
        <dl className="grid gap-1 sm:grid-cols-2">
          <div className="flex gap-2">
            <dt className="text-gray-600">Ejercicios:</dt>
            <dd className="font-mono">
              {detalle.ejercicio_desde ?? "todos"} → {detalle.ejercicio_hasta ?? "todos"}
            </dd>
          </div>
          <div className="flex gap-2">
            <dt className="text-gray-600">Generada:</dt>
            <dd>{detalle.created_at ? detalle.created_at.slice(0, 19) : "—"}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="text-gray-600">Completada:</dt>
            <dd>{detalle.completado_at ? detalle.completado_at.slice(0, 19) : "—"}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="text-gray-600">Tenant del manifiesto:</dt>
            <dd>{manifiesto.tenant_id}</dd>
          </div>
        </dl>
        <p className="break-all text-xs font-mono text-gray-700">
          SHA-256 del ZIP: {manifiesto.sha256_fichero ?? "—"}
        </p>
        <p className="break-all text-xs font-mono text-gray-700">
          Formato del manifiesto: {manifiesto.formato_version ?? "—"}
        </p>
        <div className="flex flex-wrap items-center gap-3 pt-2">
          <DescargaExport exportacion={detalle} onMensaje={setMensaje} />
          <button
            type="button"
            onClick={() => void verificar()}
            disabled={verificando}
            className="rounded border px-4 py-2 text-sm font-semibold hover:bg-gray-50 disabled:opacity-50"
          >
            {verificando ? "Verificando…" : "Verificar integridad"}
          </button>
          {detalle.tipo === "SII" && (
            <button
              type="button"
              onClick={() => void cargarSii()}
              className="rounded border px-4 py-2 text-sm font-semibold hover:bg-gray-50"
            >
              Ver datos SII
            </button>
          )}
        </div>
        {mensaje && <p className="text-xs text-emerald-700">{mensaje}</p>}
        {error && <p className="text-xs text-red-600">{error}</p>}
      </section>

      <ManifiestoEstado exportacion={detalle} verificacion={verificacion} />

      {verificacion && (
        <section className="rounded border bg-white p-4">
          <h2 className="text-sm font-semibold mb-2">Conteo por bloque</h2>
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b text-left text-gray-500">
                <th className="py-2 pr-3">Bloque</th>
                <th className="py-2 pr-3">Esperados</th>
                <th className="py-2 pr-3">Encontrados</th>
                <th className="py-2">Coincide</th>
              </tr>
            </thead>
            <tbody>
              {verificacion.bloques.map((bloque) => (
                <tr key={bloque.bloque} className="border-b">
                  <td className="py-1 pr-3">{bloque.bloque}</td>
                  <td className="py-1 pr-3">{bloque.esperados}</td>
                  <td className="py-1 pr-3">{bloque.encontrados}</td>
                  <td className="py-1">{bloque.coincide ? "sí" : "no"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <section className="rounded border bg-white p-4">
        <h2 className="text-sm font-semibold mb-2">
          Inventario de bloques ({manifiesto.n_bloques})
        </h2>
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b text-left text-gray-500">
              <th className="py-2 pr-3">Bloque</th>
              <th className="py-2 pr-3">Fichero</th>
              <th className="py-2 pr-3">Registros</th>
              <th className="py-2 pr-3">Ejercicios</th>
              <th className="py-2">Huella</th>
            </tr>
          </thead>
          <tbody>
            {manifiesto.bloques.map((bloque) => (
              <tr key={bloque.bloque} className="border-b hover:bg-gray-50">
                <td className="py-1.5 pr-3">
                  {bloque.bloque}
                  {bloque.descripcion && (
                    <span className="block text-xs text-gray-500">
                      {bloque.descripcion}
                    </span>
                  )}
                </td>
                <td className="py-1.5 pr-3 font-mono text-xs">{bloque.fichero ?? "—"}</td>
                <td className="py-1.5 pr-3">{bloque.conteo_registros}</td>
                <td className="py-1.5 pr-3 font-mono text-xs">
                  {bloque.ejercicio_min ?? "—"} → {bloque.ejercicio_max ?? "—"}
                </td>
                <td className="py-1.5 font-mono text-xs">
                  {bloque.sha256 ? `${bloque.sha256.slice(0, 12)}…` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {sii && (
        <section className="rounded border bg-white p-4 space-y-2">
          <h2 className="text-sm font-semibold">Bloque SII (subida manual a la AEAT)</h2>
          <p className="text-xs text-gray-600">
            Régimen {config?.clave_regimen} ·{" "}
            {config?.sin_anexo ? "exenta de anexos" : "con anexos"} · la
            presentación telemática queda fuera de alcance.
          </p>
          {sii.map((bloque) => (
            <details key={bloque.nombre}>
              <summary className="text-sm cursor-pointer">
                {bloque.nombre} ({bloque.conteo})
              </summary>
              <table className="w-full text-xs border-collapse mt-2">
                <thead>
                  <tr className="border-b text-left text-gray-500">
                    <th className="py-1 pr-2">NIF</th>
                    <th className="py-1 pr-2">Razón social</th>
                    <th className="py-1 pr-2">Tipo</th>
                    <th className="py-1 pr-2">Número</th>
                    <th className="py-1 pr-2">Base</th>
                    <th className="py-1 pr-2">IVA</th>
                    <th className="py-1">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {bloque.registros.map((registro) => (
                    <tr key={registro.IdFactura} className="border-b">
                      <td className="py-0.5 pr-2">{registro.NIF}</td>
                      <td className="py-0.5 pr-2">{registro.NombreRazon}</td>
                      <td className="py-0.5 pr-2">{registro.TipoFactura}</td>
                      <td className="py-0.5 pr-2 font-mono">
                        {registro.NumeroFactura}
                      </td>
                      <td className="py-0.5 pr-2 font-mono">
                        {registro.BaseImponible}
                      </td>
                      <td className="py-0.5 pr-2 font-mono">
                        {registro.CuotaRepercutida}
                      </td>
                      <td className="py-0.5 font-mono">{registro.ImporteTotal}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          ))}
        </section>
      )}
    </main>
  );
}
