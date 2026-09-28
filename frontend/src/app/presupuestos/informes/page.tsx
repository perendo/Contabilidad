"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  cerrarPeriodo,
  crearPeriodo,
  formatearImporte,
  formatearPorcentaje,
  informeDesviacion,
  listarPeriodos,
  type InformeDesviacion,
  type ListadoPeriodos,
} from "@/components/budget/api";
import CentroSelect from "@/components/costcenters/CentroSelect";

const EJERCICIO_POR_DEFECTO = new Date().getFullYear();
const MESES = [
  "Enero",
  "Febrero",
  "Marzo",
  "Abril",
  "Mayo",
  "Junio",
  "Julio",
  "Agosto",
  "Septiembre",
  "Octubre",
  "Noviembre",
  "Diciembre",
];

export default function InformesPage() {
  const [ejercicio, setEjercicio] = useState(EJERCICIO_POR_DEFECTO);
  const [mes, setMes] = useState("");
  const [centro, setCentro] = useState("");
  const [informe, setInforme] = useState<InformeDesviacion | null>(null);
  const [periodos, setPeriodos] = useState<ListadoPeriodos>({ items: [], total: 0 });
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [nuevoInicio, setNuevoInicio] = useState(`${EJERCICIO_POR_DEFECTO}-01-01`);
  const [nuevoFin, setNuevoFin] = useState(`${EJERCICIO_POR_DEFECTO}-12-31`);

  const recargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const [datos, lista] = await Promise.all([
        informeDesviacion({
          ejercicio,
          mes: mes || undefined,
          centro_coste_id: centro || undefined,
          page_size: 200,
        }),
        listarPeriodos(ejercicio),
      ]);
      setInforme(datos);
      setPeriodos(lista);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error de conexion");
    } finally {
      setCargando(false);
    }
  }, [ejercicio, mes, centro]);

  useEffect(() => {
    void recargar();
  }, [recargar]);

  const abierto = periodos.items.find((p) => p.estado === "abierto");

  async function cerrar() {
    if (!abierto?.periodo_id) return;
    const ok = window.confirm(
      `¿Cerrar el periodo ${abierto.numero_periodo} del ejercicio ${ejercicio}?\n\n` +
        "Se generara un snapshot inmutable de la desviacion y el presupuesto " +
        "dejara de ser modificable hasta abrir un periodo nuevo."
    );
    if (!ok) return;
    setError(null);
    setAviso(null);
    try {
      const resultado = await cerrarPeriodo({
        ejercicio,
        periodo_id: abierto.periodo_id,
      });
      setAviso(
        `Periodo ${resultado.numero_periodo} cerrado: ${resultado.desviaciones_registradas} desviacion(es) registradas.`
      );
      await recargar();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error de conexion");
    }
  }

  async function abrir() {
    setError(null);
    setAviso(null);
    try {
      const creado = await crearPeriodo({
        ejercicio,
        fecha_inicio: nuevoInicio,
        fecha_fin: nuevoFin,
      });
      setAviso(`Periodo ${creado.numero_periodo} abierto.`);
      await recargar();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error de conexion");
    }
  }

  return (
    <main className="p-6 max-w-6xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Informe de desviacion</h1>
        <div className="flex items-center gap-3">
          <Link className="text-sm text-blue-600 underline" href="/presupuestos">
            Presupuesto
          </Link>
          <Link
            className="text-sm text-blue-600 underline"
            href="/presupuestos/seguimiento"
          >
            Seguimiento
          </Link>
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <span className="block text-gray-600 mb-1">Ejercicio</span>
          <input
            type="number"
            className="border rounded px-2 py-1 w-24"
            value={ejercicio}
            onChange={(e) => setEjercicio(Number(e.target.value))}
          />
        </label>
        <label className="text-sm">
          <span className="block text-gray-600 mb-1">Acumulado</span>
          <select
            className="border rounded px-2 py-1"
            value={mes}
            onChange={(e) => setMes(e.target.value)}
          >
            <option value="">Todo el ejercicio</option>
            {MESES.map((nombre, indice) => (
              <option key={nombre} value={indice + 1}>
                Hasta {nombre}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <span className="block text-gray-600 mb-1">Centro de coste</span>
          <CentroSelect value={centro} onChange={setCentro} />
        </label>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}
      {aviso && <p className="text-sm text-emerald-700">{aviso}</p>}

      <section className="rounded border p-4 space-y-2">
        <h2 className="font-medium">Cierre de seguimiento</h2>
        {periodos.total === 0 ? (
          <p className="text-sm text-gray-500">
            El ejercicio {ejercicio} todavia no tiene periodos de seguimiento.
          </p>
        ) : (
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b text-left text-gray-500">
                <th className="py-1.5 pr-3">Nº</th>
                <th className="py-1.5 pr-3">Rango</th>
                <th className="py-1.5 pr-3">Estado</th>
                <th className="py-1.5 pr-3">Cierre</th>
                <th className="py-1.5">Desviaciones</th>
              </tr>
            </thead>
            <tbody>
              {periodos.items.map((p) => (
                <tr key={p.periodo_id ?? p.numero_periodo} className="border-b">
                  <td className="py-1.5 pr-3 font-mono">{p.numero_periodo}</td>
                  <td className="py-1.5 pr-3">
                    {p.fecha_inicio} → {p.fecha_fin}
                  </td>
                  <td className="py-1.5 pr-3">{p.estado}</td>
                  <td className="py-1.5 pr-3">
                    {p.fecha_cierre ? `${p.fecha_cierre} (${p.cerrado_por})` : "—"}
                  </td>
                  <td className="py-1.5">{p.desviaciones_registradas}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="flex flex-wrap items-end gap-3 pt-2">
          <button
            type="button"
            onClick={() => void cerrar()}
            disabled={!abierto}
            className="rounded bg-red-600 px-3 py-1.5 text-sm text-white hover:bg-red-700 disabled:opacity-50"
          >
            Cerrar periodo abierto
          </button>
          <label className="text-sm">
            <span className="block text-gray-600 mb-1">Nuevo desde</span>
            <input
              type="date"
              className="border rounded px-2 py-1"
              value={nuevoInicio}
              onChange={(e) => setNuevoInicio(e.target.value)}
            />
          </label>
          <label className="text-sm">
            <span className="block text-gray-600 mb-1">hasta</span>
            <input
              type="date"
              className="border rounded px-2 py-1"
              value={nuevoFin}
              onChange={(e) => setNuevoFin(e.target.value)}
            />
          </label>
          <button
            type="button"
            onClick={() => void abrir()}
            disabled={Boolean(abierto)}
            className="rounded border px-3 py-1.5 text-sm hover:bg-gray-50 disabled:opacity-50"
          >
            Abrir periodo
          </button>
        </div>
      </section>

      {cargando ? (
        <p className="text-sm text-gray-500">Cargando…</p>
      ) : (
        informe && (
          <>
            <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="rounded border p-3">
                <p className="text-xs text-gray-500">Presupuestado</p>
                <p className="font-mono text-lg">
                  {formatearImporte(informe.total_presupuestado)}
                </p>
              </div>
              <div className="rounded border p-3">
                <p className="text-xs text-gray-500">Real</p>
                <p className="font-mono text-lg">
                  {formatearImporte(informe.total_real)}
                </p>
              </div>
              <div className="rounded border p-3">
                <p className="text-xs text-gray-500">Desviacion</p>
                <p
                  className={`font-mono text-lg ${
                    Number(informe.total_desviacion) > 0
                      ? "text-red-700"
                      : "text-emerald-700"
                  }`}
                >
                  {formatearImporte(informe.total_desviacion)}
                </p>
              </div>
              <div className="rounded border p-3">
                <p className="text-xs text-gray-500">Sin presupuestar</p>
                <p className="font-mono text-lg">
                  {informe.lineas_sin_presupuesto}
                </p>
              </div>
            </section>

            <section className="space-y-2">
              <h2 className="font-medium">Por centro de coste</h2>
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="border-b text-left text-gray-500">
                    <th className="py-2 pr-3">Centro</th>
                    <th className="py-2 pr-3 text-right">Presupuestado</th>
                    <th className="py-2 pr-3 text-right">Real</th>
                    <th className="py-2 pr-3 text-right">Desviacion</th>
                    <th className="py-2 text-right">Lineas</th>
                  </tr>
                </thead>
                <tbody>
                  {informe.centros.map((c) => (
                    <tr key={c.centro_coste_id ?? "sin"} className="border-b">
                      <td className="py-1.5 pr-3">{c.nombre_centro}</td>
                      <td className="py-1.5 pr-3 text-right font-mono">
                        {c.importe_presupuestado}
                      </td>
                      <td className="py-1.5 pr-3 text-right font-mono">
                        {c.importe_real}
                      </td>
                      <td className="py-1.5 pr-3 text-right font-mono">
                        {c.desviacion_absoluta}
                      </td>
                      <td className="py-1.5 text-right">{c.lineas}</td>
                    </tr>
                  ))}
                  {informe.centros.length === 0 && (
                    <tr>
                      <td colSpan={5} className="py-4 text-gray-500">
                        Sin datos para el informe.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </section>

            <section className="space-y-2">
              <h2 className="font-medium">Detalle por cuenta ({informe.total})</h2>
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="border-b text-left text-gray-500">
                    <th className="py-2 pr-3">Cuenta</th>
                    <th className="py-2 pr-3">Centro</th>
                    <th className="py-2 pr-3 text-right">Presupuestado</th>
                    <th className="py-2 pr-3 text-right">Real</th>
                    <th className="py-2 pr-3 text-right">Desviacion</th>
                    <th className="py-2 pr-3 text-right">Relativa</th>
                    <th className="py-2">Sin presupuesto</th>
                  </tr>
                </thead>
                <tbody>
                  {informe.items.map((item) => (
                    <tr
                      key={`${item.cuenta_id}-${item.centro_coste_id ?? "sin"}`}
                      className="border-b hover:bg-gray-50"
                    >
                      <td className="py-1.5 pr-3 font-mono">
                        {item.codigo_cuenta}
                      </td>
                      <td className="py-1.5 pr-3">
                        {item.nombre_centro ?? "— sin centro —"}
                      </td>
                      <td className="py-1.5 pr-3 text-right font-mono">
                        {item.importe_presupuestado}
                      </td>
                      <td className="py-1.5 pr-3 text-right font-mono">
                        {item.importe_real}
                      </td>
                      <td className="py-1.5 pr-3 text-right font-mono">
                        {item.desviacion_absoluta}
                      </td>
                      <td className="py-1.5 pr-3 text-right font-mono">
                        {formatearPorcentaje(item.desviacion_relativa)}
                      </td>
                      <td className="py-1.5">
                        {item.sin_presupuesto ? "si" : "no"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>

            <p className="text-xs text-gray-500">
              Origen: {informe.origen} · cuadra (real - presupuestado = desviacion):{" "}
              {informe.cuadra ? "si" : "no"}
            </p>
          </>
        )
      )}
    </main>
  );
}
