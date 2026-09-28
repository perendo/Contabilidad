"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  EJERCICIO_POR_DEFECTO,
  crearExportacion,
  formatearBytes,
  obtenerConfigSii,
  type ConfigSii,
  type Exportacion,
  type TipoExportacion,
} from "@/components/export/api";

/** T024 + T045: alta de exportacion, selector de tipo y aviso de configuracion SII. */
export default function NuevaExportacionPage() {
  const router = useRouter();
  const [tipo, setTipo] = useState<TipoExportacion>("INTEGRAL");
  const [usarRango, setUsarRango] = useState(false);
  const [desde, setDesde] = useState(EJERCICIO_POR_DEFECTO);
  const [hasta, setHasta] = useState(EJERCICIO_POR_DEFECTO);
  const [config, setConfig] = useState<ConfigSii | null>(null);
  const [creando, setCreando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [creada, setCreada] = useState<Exportacion | null>(null);

  const cargarConfig = useCallback(async () => {
    try {
      setConfig(await obtenerConfigSii());
    } catch {
      setConfig(null);
    }
  }, []);

  useEffect(() => {
    void cargarConfig();
  }, [cargarConfig]);

  const sinSii = tipo === "SII" && config !== null && !config.obligado_sii;

  async function crear() {
    setCreando(true);
    setError(null);
    setAviso(null);
    setCreada(null);
    try {
      const cuerpo: {
        tipo: TipoExportacion;
        ejercicio_desde?: number;
        ejercicio_hasta?: number;
      } = { tipo };
      if (usarRango) {
        cuerpo.ejercicio_desde = desde;
        cuerpo.ejercicio_hasta = hasta;
      }
      const exportacion = await crearExportacion(cuerpo);
      setCreada(exportacion);
      setAviso(
        `Exportación ${exportacion.anio_creacion}/${exportacion.numero_exportacion} generada ` +
          `con ${exportacion.n_bloques} bloques (${formatearBytes(exportacion.tamano_bytes)}).`
      );
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "No se pudo generar la exportación"
      );
    } finally {
      setCreando(false);
    }
  }

  return (
    <main className="p-6 max-w-3xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Nueva exportación</h1>
          <p className="text-sm text-gray-500">
            Genera el ZIP con todos los datos de la empresa activa
          </p>
        </div>
        <Link className="text-blue-600 underline" href="/exportaciones">
          Exportaciones
        </Link>
      </div>

      <section className="rounded border bg-white p-4 space-y-3">
        <label className="block text-sm">
          <span className="block text-gray-600 mb-1">Tipo</span>
          <select
            className="border rounded px-2 py-1"
            value={tipo}
            onChange={(e) => setTipo(e.target.value as TipoExportacion)}
          >
            <option value="INTEGRAL">Integral (17 bloques)</option>
            <option value="SII">SII de la AEAT</option>
          </select>
        </label>

        {tipo === "SII" && config !== null && (
          <p
            className={`rounded border p-3 text-xs ${
              config.obligado_sii
                ? "border-green-300 bg-green-50 text-green-800"
                : "border-amber-300 bg-amber-50 text-amber-800"
            }`}
          >
            {config.obligado_sii
              ? `Configuración SII: régimen ${config.clave_regimen}` +
                (config.sin_anexo ? " · exenta de anexos" : " · con anexos") +
                ". Se exportarán también datos_sii/facturas_emitidas.json y facturas_recibidas.json."
              : "La empresa no está obligada al SII: el backend rechazará la exportación (422) hasta configurar ConfigSii."}
          </p>
        )}

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={usarRango}
            onChange={(e) => setUsarRango(e.target.checked)}
          />
          <span>Limitar a un rango de ejercicios (FR-005)</span>
        </label>

        {usarRango && (
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-sm">
              <span className="block text-gray-600 mb-1">Desde</span>
              <input
                type="number"
                className="border rounded px-2 py-1 w-24"
                value={desde}
                onChange={(e) => setDesde(Number(e.target.value))}
              />
            </label>
            <label className="text-sm">
              <span className="block text-gray-600 mb-1">Hasta</span>
              <input
                type="number"
                className="border rounded px-2 py-1 w-24"
                value={hasta}
                onChange={(e) => setHasta(Number(e.target.value))}
              />
            </label>
            <p className="text-xs text-gray-500">
              Los bloques atemporales (plan de cuentas, terceros, configuración) se
              exportan igualmente completos.
            </p>
          </div>
        )}

        <button
          type="button"
          onClick={() => void crear()}
          disabled={creando || sinSii}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {creando ? "Generando…" : "Crear exportación"}
        </button>
        {creando && (
          <p className="text-xs text-gray-500">
            Se están recopilando los 17 bloques y comprimiendo el ZIP. Puede tardar
            unos segundos en un tenant grande.
          </p>
        )}
      </section>

      {error && <p className="text-sm text-red-600">{error}</p>}
      {aviso && <p className="text-sm text-emerald-700">{aviso}</p>}

      {creada && (
        <section className="rounded border border-green-300 bg-green-50 p-4 text-green-800 text-sm space-y-1">
          <p className="font-semibold">Exportación lista</p>
          <p className="text-xs font-mono break-all">Huella SHA-256: {creada.sha256}</p>
          <p className="text-xs font-mono break-all">
            Contenido: {creada.sha256_contenido}
          </p>
          <button
            type="button"
            onClick={() => router.push(`/exportaciones/${creada.exportacion_id}`)}
            className="rounded border border-green-400 px-3 py-1 text-xs font-semibold"
          >
            Ver detalle y descargar
          </button>
        </section>
      )}
    </main>
  );
}
