"use client";

/**
 * IMPORTAR Y EXPORTAR ASIENTOS (SPEC-031, US6, T056)
 *
 * Ruta canónica: `/asientos/import-export`. La anterior era
 * `/contabilidad/import-export`, y esta vive en `/asientos` porque la pantalla trata
 * **asientos**, no contabilidad en general: cualquiera que llegue por el libro diario
 * la encuentra junto a sus vecinos, que es lo que hace la navegación predecible.
 *
 * La ruta vieja se conserva como redirect permanente en `next.config.mjs` (T055), así que
 * los enlaces y marcadores que apuntaban allí siguen llegando aquí.
 *
 * Los imports son absolutos con `@/`. Los relativos que tenía antes eran de tres niveles
 * (`../../../components/...`) y desde aquí son dos: con relativos, el error de profundidad
 * solo aparecería en ejecución, cuando el módulo no se encuentra.
 */
import { useState } from "react";

import { ApiError } from "@/components/treasury/api";
import ResultadoImport, {
  type ResultadoPrevisualizacion,
} from "@/components/importexport/ResultadoImport";
import { cabecerasEmpresa } from "@/components/treasury/empresa";
import { getToken } from "@/services/client";

interface ResultadoDefinitiva {
  asientos_importados: number;
  asientos_omitidos: number;
  primer_numero_asiento: number | null;
  ultimo_numero_asiento: number | null;
}

async function subirArchivo<T>(ruta: string, archivo: File): Promise<T> {
  const datos = new FormData();
  datos.append("archivo", archivo);
  const cabeceras: Record<string, string> = { ...cabecerasEmpresa() };
  const token = getToken();
  if (token) cabeceras["Authorization"] = `Bearer ${token}`;
  const respuesta = await fetch(ruta, { method: "POST", headers: cabeceras, body: datos });
  const cuerpo = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    const detalle = (cuerpo as { detail?: unknown })?.detail;
    throw new ApiError(
      respuesta.status,
      typeof detalle === "string" ? detalle : "Error al procesar el archivo"
    );
  }
  return cuerpo as T;
}

export default function ImportExportPage() {
  const [archivo, setArchivo] = useState<File | null>(null);
  const [previa, setPrevia] = useState<ResultadoPrevisualizacion | null>(null);
  const [definitiva, setDefinitiva] = useState<ResultadoDefinitiva | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);

  async function previsualizar(file: File) {
    setError(null);
    setDefinitiva(null);
    setCargando(true);
    try {
      setPrevia(
        await subirArchivo<ResultadoPrevisualizacion>(
          "/api/v1/asientos/importar/previsualizar",
          file
        )
      );
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    } finally {
      setCargando(false);
    }
  }

  async function confirmar() {
    if (!archivo) return;
    setError(null);
    setCargando(true);
    try {
      const resultado = await subirArchivo<ResultadoDefinitiva>(
        "/api/v1/asientos/importar/confirmar",
        archivo
      );
      setDefinitiva(resultado);
      setPrevia(null);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    } finally {
      setCargando(false);
    }
  }

  return (
    <main className="p-6 max-w-4xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Importar / Exportar asientos</h1>
      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          const file = e.dataTransfer.files[0];
          if (file) {
            setArchivo(file);
            previsualizar(file);
          }
        }}
        className="border-2 border-dashed rounded p-8 text-center mb-4"
      >
        <p className="mb-2">Arrastra aquí un CSV o XLSX, o selecciona un archivo</p>
        <input
          type="file"
          accept=".csv,.xlsx,.xlsm"
          onChange={(e) => {
            const file = e.target.files?.[0] ?? null;
            setArchivo(file);
            if (file) previsualizar(file);
          }}
        />
      </div>
      {error && <p className="text-red-600 mb-4">{error}</p>}
      {cargando && <p className="mb-4">Procesando…</p>}
      {previa && (
        <>
          <ResultadoImport resultado={previa} />
          <button
            onClick={confirmar}
            disabled={previa.asientos_validos === 0}
            className="mt-4 bg-blue-600 text-white rounded px-3 py-1 disabled:opacity-50"
          >
            Confirmar importación
          </button>
        </>
      )}
      {definitiva && (
        <p className="text-emerald-700">
          Importados {definitiva.asientos_importados} · Omitidos{" "}
          {definitiva.asientos_omitidos}
          {definitiva.primer_numero_asiento !== null &&
            ` · Números ${definitiva.primer_numero_asiento}–${definitiva.ultimo_numero_asiento}`}
        </p>
      )}
    </main>
  );
}