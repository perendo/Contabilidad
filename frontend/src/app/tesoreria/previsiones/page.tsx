"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  formatearImporte,
  generarPrevision,
  Granularidad,
  Granularidad as TipoGranularidad,
  listarPrevisiones,
  MovimientoManual,
  MOTIVOS_EXCLUSION,
  Prevision,
  ResultadoGenerar,
} from "@/components/cashflow/api";

const HOY = new Date().toISOString().slice(0, 10);
const EN_TRES_MESES = () => {
  const fecha = new Date();
  fecha.setMonth(fecha.getMonth() + 3);
  return fecha.toISOString().slice(0, 10);
};

const GRANULARIDADES: { valor: TipoGranularidad; etiqueta: string }[] = [
  { valor: "dia", etiqueta: "Día" },
  { valor: "semana", etiqueta: "Semana" },
  { valor: "mes", etiqueta: "Mes" },
];

export default function PrevisionesTesoreriaPage() {
  const [items, setItems] = useState<Prevision[]>([]);
  const [total, setTotal] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filtroGranularidad, setFiltroGranularidad] = useState<"" | Granularidad>("");

  const [desde, setDesde] = useState(HOY);
  const [hasta, setHasta] = useState(EN_TRES_MESES());
  const [granularidad, setGranularidad] = useState<TipoGranularidad>("dia");
  const [incluirPago, setIncluirPago] = useState(false);
  const [pagoImporte, setPagoImporte] = useState("1200.0000");
  const [pagoFecha, setPagoFecha] = useState("");
  const [pagoFrecuencia, setPagoFrecuencia] = useState<"unico" | "mensual">("unico");
  const [pagoConcepto, setPagoConcepto] = useState("");
  const [generando, setGenerando] = useState(false);
  const [ultima, setUltima] = useState<ResultadoGenerar | null>(null);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const respuesta = await listarPrevisiones(
        filtroGranularidad ? { granularidad: filtroGranularidad } : {}
      );
      setItems(respuesta.items);
      setTotal(respuesta.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar las previsiones");
    } finally {
      setCargando(false);
    }
  }, [filtroGranularidad]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const generar = async () => {
    setGenerando(true);
    setError(null);
    try {
      const manuales: MovimientoManual[] = incluirPago
        ? [
            {
              tipo: "pago",
              importe: pagoImporte,
              fecha_prevista: pagoFecha || null,
              frecuencia: pagoFrecuencia,
              concepto: pagoConcepto || null,
            },
          ]
        : [];
      const respuesta = await generarPrevision({
        desde_fecha: desde,
        hasta_fecha: hasta,
        granularidad,
        movimientos_manuales: manuales,
      });
      setUltima(respuesta);
      setPagoFecha("");
      setPagoConcepto("");
      await cargar();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo generar la previsión");
    } finally {
      setGenerando(false);
    }
  };

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Previsión de Tesorería</h1>
          <p className="text-sm text-gray-500">
            Proyección de cobros y pagos previstos a partir de los vencimientos pendientes
          </p>
        </div>
        <Link
          href="/tesoreria"
          className="rounded border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
        >
          Panel de tesorería
        </Link>
      </div>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 p-4 text-red-700">{error}</div>
      )}

      {/* Generador */}
      <section className="rounded border bg-white p-5">
        <h2 className="text-lg font-semibold">Generar previsión</h2>
        <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-4">
          <label className="text-sm">
            <span className="block font-medium text-gray-700">Desde</span>
            <input
              type="date"
              value={desde}
              onChange={(e) => setDesde(e.target.value)}
              className="mt-1 w-full rounded border px-2 py-1"
            />
          </label>
          <label className="text-sm">
            <span className="block font-medium text-gray-700">Hasta</span>
            <input
              type="date"
              value={hasta}
              onChange={(e) => setHasta(e.target.value)}
              className="mt-1 w-full rounded border px-2 py-1"
            />
          </label>
          <label className="text-sm">
            <span className="block font-medium text-gray-700">Granularidad</span>
            <select
              value={granularidad}
              onChange={(e) => setGranularidad(e.target.value as TipoGranularidad)}
              className="mt-1 w-full rounded border px-2 py-1"
            >
              {GRANULARIDADES.map((opcion) => (
                <option key={opcion.valor} value={opcion.valor}>
                  {opcion.etiqueta}
                </option>
              ))}
            </select>
          </label>
          <div className="flex items-end">
            <button
              onClick={generar}
              disabled={generando}
              className="w-full rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {generando ? "Generando..." : "Generar"}
            </button>
          </div>
        </div>

        <div className="mt-4 rounded border border-dashed p-3">
          <label className="flex items-center gap-2 text-sm font-medium text-gray-700">
            <input
              type="checkbox"
              checked={incluirPago}
              onChange={(e) => setIncluirPago(e.target.checked)}
            />
            Añadir un pago previsto (alquiler, nómina...)
          </label>
          {incluirPago && (
            <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-4">
              <input
                placeholder="Importe (1200.0000)"
                value={pagoImporte}
                onChange={(e) => setPagoImporte(e.target.value)}
                className="rounded border px-2 py-1 text-sm"
              />
              <input
                type="date"
                value={pagoFecha}
                onChange={(e) => setPagoFecha(e.target.value)}
                className="rounded border px-2 py-1 text-sm"
              />
              <select
                value={pagoFrecuencia}
                onChange={(e) =>
                  setPagoFrecuencia(e.target.value as "unico" | "mensual")
                }
                className="rounded border px-2 py-1 text-sm"
              >
                <option value="unico">Pago único</option>
                <option value="mensual">Pago mensual</option>
              </select>
              <input
                placeholder="Concepto"
                value={pagoConcepto}
                onChange={(e) => setPagoConcepto(e.target.value)}
                className="rounded border px-2 py-1 text-sm"
              />
            </div>
          )}
          <p className="mt-2 text-xs text-gray-400">
            Un pago previsto sin fecha se excluye de la proyección y se reporta con su motivo.
          </p>
        </div>
      </section>

      {/* Resultado de la última generación */}
      {ultima && (
        <section className="rounded border border-blue-200 bg-blue-50 p-5">
          <h2 className="text-lg font-semibold">
            Previsión nº {ultima.numero_prevision} generada
          </h2>
          <div className="mt-2 grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
            <div>
              <div className="text-xs uppercase text-gray-500">Saldo inicial</div>
              <div className="font-mono">{formatearImporte(ultima.saldo_inicial)}</div>
            </div>
            <div>
              <div className="text-xs uppercase text-gray-500">Saldo final</div>
              <div className="font-mono font-bold">{formatearImporte(ultima.saldo_final)}</div>
            </div>
            <div>
              <div className="text-xs uppercase text-gray-500">Movimientos</div>
              <div className="font-mono">{ultima.n_movimientos}</div>
            </div>
            <div>
              <div className="text-xs uppercase text-gray-500">Alertas</div>
              <div className="font-mono">{ultima.n_alertas}</div>
            </div>
          </div>
          {ultima.excluidos.length > 0 && (
            <ul className="mt-3 space-y-1 text-xs text-gray-600">
              {ultima.excluidos.map((excluido, indice) => (
                <li key={indice}>
                  <span className="font-semibold">{excluido.origen}</span> ·{" "}
                  {MOTIVOS_EXCLUSION[excluido.motivo] ?? excluido.motivo} ·{" "}
                  {formatearImporte(excluido.importe)}
                </li>
              ))}
            </ul>
          )}
          <Link
            href={`/tesoreria/previsiones/${ultima.id}`}
            className="mt-3 inline-block text-sm font-semibold text-blue-700 hover:underline"
          >
            Ver detalle →
          </Link>
        </section>
      )}

      {/* Listado */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Previsiones ({total})</h2>
          <select
            value={filtroGranularidad}
            onChange={(e) => setFiltroGranularidad(e.target.value as "" | Granularidad)}
            className="rounded border px-2 py-1 text-sm"
          >
            <option value="">Todas las granularidades</option>
            {GRANULARIDADES.map((opcion) => (
              <option key={opcion.valor} value={opcion.valor}>
                {opcion.etiqueta}
              </option>
            ))}
          </select>
        </div>
        <div className="overflow-x-auto rounded border bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b bg-gray-100 text-xs uppercase text-gray-600">
              <tr>
                <th className="p-3">Nº</th>
                <th className="p-3">Rango</th>
                <th className="p-3">Granularidad</th>
                <th className="p-3 text-right">Saldo inicial</th>
                <th className="p-3 text-right">Saldo final</th>
                <th className="p-3">Estado</th>
                <th className="p-3" />
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td colSpan={7} className="p-6 text-center text-gray-400">
                    No hay previsiones para la empresa activa
                  </td>
                </tr>
              ) : (
                items.map((prevision) => (
                  <tr key={prevision.id} className="border-b hover:bg-gray-50">
                    <td className="p-3 font-mono">{prevision.numero_prevision}</td>
                    <td className="p-3 text-gray-600">
                      {prevision.desde_fecha} → {prevision.hasta_fecha}
                    </td>
                    <td className="p-3">{prevision.granularidad}</td>
                    <td className="p-3 text-right font-mono">
                      {formatearImporte(prevision.saldo_inicial)}
                    </td>
                    <td className="p-3 text-right font-mono font-semibold">
                      {formatearImporte(prevision.saldo_final)}
                    </td>
                    <td className="p-3">{prevision.estado}</td>
                    <td className="p-3 text-right">
                      <Link
                        href={`/tesoreria/previsiones/${prevision.id}`}
                        className="text-blue-600 hover:underline"
                      >
                        Ver
                      </Link>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {cargando && <p className="text-sm text-gray-500">Cargando…</p>}
      </section>
    </div>
  );
}
