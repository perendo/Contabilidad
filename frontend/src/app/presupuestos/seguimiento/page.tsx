"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  formatearImporte,
  formatearPorcentaje,
  periodoActual,
  seguimiento,
  type Desviacion,
  type Periodo,
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

export default function SeguimientoPage() {
  const [ejercicio, setEjercicio] = useState(EJERCICIO_POR_DEFECTO);
  const [mes, setMes] = useState("");
  const [cuentaId, setCuentaId] = useState("");
  const [centro, setCentro] = useState("");
  const [items, setItems] = useState<Desviacion[]>([]);
  const [total, setTotal] = useState(0);
  const [rango, setRango] = useState({ desde: "", hasta: "" });
  const [periodo, setPeriodo] = useState<Periodo | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const recargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const [datos, periodoActual_] = await Promise.all([
        seguimiento({
          ejercicio,
          cuenta_id: cuentaId || undefined,
          centro_coste_id: centro || undefined,
          mes: mes || undefined,
          page_size: 200,
        }),
        periodoActual(ejercicio),
      ]);
      setItems(datos.items);
      setTotal(datos.total);
      setRango({ desde: datos.desde, hasta: datos.hasta });
      setPeriodo(periodoActual_);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error de conexion");
    } finally {
      setCargando(false);
    }
  }, [ejercicio, cuentaId, centro, mes]);

  useEffect(() => {
    void recargar();
  }, [recargar]);

  return (
    <main className="p-6 max-w-6xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Seguimiento presupuesto vs real</h1>
        <div className="flex items-center gap-3">
          <Link className="text-sm text-blue-600 underline" href="/presupuestos">
            Presupuesto
          </Link>
          <Link
            className="text-sm text-blue-600 underline"
            href="/presupuestos/informes"
          >
            Informes
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
          <span className="block text-gray-600 mb-1">Mes (acumulado del mes)</span>
          <select
            className="border rounded px-2 py-1"
            value={mes}
            onChange={(e) => setMes(e.target.value)}
          >
            <option value="">Todo el ejercicio</option>
            {MESES.map((nombre, indice) => (
              <option key={nombre} value={indice + 1}>
                {nombre}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <span className="block text-gray-600 mb-1">Cuenta (id)</span>
          <input
            className="border rounded px-2 py-1 w-40"
            placeholder="id de cuenta"
            value={cuentaId}
            onChange={(e) => setCuentaId(e.target.value)}
          />
        </label>
        <label className="text-sm">
          <span className="block text-gray-600 mb-1">Centro de coste</span>
          <CentroSelect value={centro} onChange={setCentro} />
        </label>
      </div>

      <p className="text-sm text-gray-600">
        Periodo {periodo ? `${periodo.numero_periodo} (${periodo.estado})` : "—"} ·
        real acumulado de {rango.desde || "—"} a {rango.hasta || "—"}.
      </p>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {cargando ? (
        <p className="text-sm text-gray-500">Cargando…</p>
      ) : (
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
            {items.map((item) => (
              <tr
                key={`${item.cuenta_id}-${item.centro_coste_id ?? "sin"}`}
                className="border-b hover:bg-gray-50"
              >
                <td className="py-1.5 pr-3 font-mono">{item.codigo_cuenta}</td>
                <td className="py-1.5 pr-3">
                  {item.nombre_centro ?? "— sin centro —"}
                </td>
                <td className="py-1.5 pr-3 text-right font-mono">
                  {formatearImporte(item.importe_presupuestado)}
                </td>
                <td className="py-1.5 pr-3 text-right font-mono">
                  {formatearImporte(item.importe_real)}
                </td>
                <td
                  className={`py-1.5 pr-3 text-right font-mono ${
                    Number(item.desviacion_absoluta) > 0
                      ? "text-red-700"
                      : Number(item.desviacion_absoluta) < 0
                        ? "text-emerald-700"
                        : ""
                  }`}
                >
                  {formatearImporte(item.desviacion_absoluta)}
                </td>
                <td className="py-1.5 pr-3 text-right font-mono">
                  {formatearPorcentaje(item.desviacion_relativa)}
                </td>
                <td className="py-1.5">
                  {item.sin_presupuesto ? (
                    <span className="rounded bg-amber-100 text-amber-800 px-2 py-0.5 text-xs">
                      si
                    </span>
                  ) : (
                    "no"
                  )}
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={7} className="py-4 text-gray-500">
                  Sin desviaciones para los filtros seleccionados.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}

      <p className="text-xs text-gray-500">
        {items.length} de {total} combinacion(es). La desviacion es{" "}
        <code>real - presupuesto</code>; positiva significa sobregasto.
      </p>
    </main>
  );
}
