"use client";

import { Suspense, useMemo, useState } from "react";

import {
  descargarInforme,
  informeCostes,
  type InformeCostes,
} from "../../../components/costcenters/api";
import CentroSelect from "../../../components/costcenters/CentroSelect";
import { ApiError } from "../../../components/treasury/api";

const TIPOS_INFORME = [
  ["todos", "Costes + ingresos"],
  ["coste", "Solo costes"],
  ["ingreso", "Solo ingresos"],
] as const;

function Informe() {
  const [ejercicio, setEjercicio] = useState(new Date().getFullYear());
  const [fechaDesde, setFechaDesde] = useState("");
  const [fechaHasta, setFechaHasta] = useState("");
  const [centroId, setCentroId] = useState("");
  const [tipo, setTipo] = useState<string>("todos");
  const [informe, setInforme] = useState<InformeCostes | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);

  const parametros = useMemo(() => {
    const p: Record<string, string | number> = { ejercicio, tipo };
    if (fechaDesde) p.fecha_desde = fechaDesde;
    if (fechaHasta) p.fecha_hasta = fechaHasta;
    if (centroId) p.centro_id = centroId;
    return p;
  }, [ejercicio, fechaDesde, fechaHasta, centroId, tipo]);

  async function consultar() {
    setError(null);
    setCargando(true);
    try {
      setInforme(await informeCostes(parametros));
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    } finally {
      setCargando(false);
    }
  }

  async function exportar() {
    setError(null);
    try {
      await descargarInforme({ ...parametros, format: "csv" });
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("No se pudo exportar el informe");
    }
  }

  const filas = informe?.filas ?? [];
  const totales = informe?.totales;

  return (
    <div className="flex flex-col gap-4">
      {error && <p className="text-red-600">{error}</p>}
      <div className="flex flex-wrap gap-3 items-end">
        <label className="flex flex-col gap-1">
          Ejercicio
          <input
            type="number"
            value={ejercicio}
            onChange={(e) => setEjercicio(Number(e.target.value))}
            className="border rounded px-3 py-1 w-32 font-mono"
          />
        </label>
        <label className="flex flex-col gap-1">
          Desde
          <input
            type="date"
            value={fechaDesde}
            onChange={(e) => setFechaDesde(e.target.value)}
            className="border rounded px-3 py-1"
          />
        </label>
        <label className="flex flex-col gap-1">
          Hasta
          <input
            type="date"
            value={fechaHasta}
            onChange={(e) => setFechaHasta(e.target.value)}
            className="border rounded px-3 py-1"
          />
        </label>
        <CentroSelect value={centroId} onChange={setCentroId} soloActivos={false} />
        <label className="flex flex-col gap-1">
          Tipo
          <select
            value={tipo}
            onChange={(e) => setTipo(e.target.value)}
            className="border rounded px-3 py-1"
          >
            {TIPOS_INFORME.map(([valor, etiqueta]) => (
              <option key={valor} value={valor}>
                {etiqueta}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={() => void consultar()}
          disabled={cargando}
          className="bg-blue-600 text-white rounded px-4 py-1 disabled:opacity-50"
        >
          Generar
        </button>
        <button
          type="button"
          onClick={() => void exportar()}
          disabled={!informe}
          className="border rounded px-4 py-1 disabled:opacity-50"
        >
          Exportar CSV
        </button>
      </div>
      {cargando && <p className="text-gray-500">Generando…</p>}
      {!cargando && informe && (
        <>
          <div className="text-sm text-gray-600">
            {informe.n_filas} filas · coste {totales?.coste} · ingreso{" "}
            {totales?.ingreso} · neto {totales?.neto}
          </div>
          <table className="border-collapse text-sm w-full max-w-6xl">
            <thead>
              <tr className="border-b text-left">
                <th className="py-1 pr-3">Código</th>
                <th className="py-1 pr-3">Nombre</th>
                <th className="py-1 pr-3 text-right">Directo</th>
                <th className="py-1 pr-3 text-right">Hijos</th>
                <th className="py-1 pr-3 text-right">Subtotal</th>
              </tr>
            </thead>
            <tbody>
              {filas.map((f) => (
                <tr key={f.centro_id} className="border-b">
                  <td className="py-1 pr-3 font-mono">{f.codigo}</td>
                  <td className="py-1 pr-3">{f.nombre}</td>
                  <td className="py-1 pr-3 text-right font-mono">
                    {tipo === "ingreso" ? f.directo_haber : f.directo_debe}
                  </td>
                  <td className="py-1 pr-3 text-right font-mono">
                    {tipo === "ingreso" ? f.hijos_haber : f.hijos_debe}
                  </td>
                  <td className="py-1 pr-3 text-right font-mono font-semibold">
                    {tipo === "ingreso" ? f.subtotal_haber : f.subtotal_debe}
                  </td>
                </tr>
              ))}
              {filas.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-4 text-gray-500">
                    Sin imputaciones en el período para el centro seleccionado.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

export default function InformeCostesPage() {
  return (
    <main className="p-6 max-w-6xl mx-auto">
      <h1 className="text-xl font-semibold mb-6">Informe de costes por centro</h1>
      <Suspense fallback={null}>
        <Informe />
      </Suspense>
    </main>
  );
}