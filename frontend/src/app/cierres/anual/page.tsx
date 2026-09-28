"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  cerrarEjercicioAnual,
  formatearImporte,
  listarPeriodos,
  MESES,
  obtenerCierreAnual,
  type CierreEjercicio,
  type PeriodoCerrado,
} from "@/components/closing/api";

const EJERCICIO_POR_DEFECTO = new Date().getFullYear();

export default function CierreAnualPage() {
  const [ejercicio, setEjercicio] = useState(EJERCICIO_POR_DEFECTO);
  const [cierre, setCierre] = useState<CierreEjercicio | null>(null);
  const [periodos, setPeriodos] = useState<PeriodoCerrado[]>([]);
  const [cargando, setCargando] = useState(true);
  const [ejecutando, setEjecutando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const lista = await listarPeriodos({ ejercicio, page_size: 12 });
      setPeriodos(lista.items);
      try {
        setCierre(await obtenerCierreAnual(ejercicio));
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) setCierre(null);
        else throw e;
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "No se pudo cargar el ejercicio");
    } finally {
      setCargando(false);
    }
  }, [ejercicio]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const pendientes = periodos.filter((p) => p.estado === "abierto");
  const listoParaCerrar = periodos.length > 0 && pendientes.length === 0;

  async function ejecutar() {
    const ok = window.confirm(
      `¿Cerrar el ejercicio ${ejercicio}?\n\n` +
        "Se generaran el asiento de regularizacion y el de cierre, el ejercicio " +
        "quedara bloqueado y se generara la apertura del siguiente."
    );
    if (!ok) return;
    setEjecutando(true);
    setError(null);
    setAviso(null);
    try {
      const resultado = await cerrarEjercicioAnual({ ejercicio });
      setCierre(resultado);
      setAviso(
        `Ejercicio cerrado con resultado ${resultado.resultado_ejercicio} y ` +
          "apertura generada."
      );
      await cargar();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "No se pudo cerrar el ejercicio");
    } finally {
      setEjecutando(false);
    }
  }

  return (
    <main className="p-6 max-w-5xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Cierre anual</h1>
          <p className="text-sm text-gray-500">
            Regularizacion, cierre de saldos, bloqueo del ejercicio y apertura del
            siguiente
          </p>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <Link className="text-blue-600 underline" href="/cierres">
            Cierres
          </Link>
          <Link className="text-blue-600 underline" href="/cierres/intermedio">
            Intermedio
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
        <button
          type="button"
          onClick={cargar}
          className="rounded border px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
        >
          Consultar
        </button>
        <button
          type="button"
          onClick={() => void ejecutar()}
          disabled={ejecutando || cargando || !listoParaCerrar || cierre !== null}
          className="rounded bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
        >
          {ejecutando ? "Cerrando…" : "Cerrar ejercicio"}
        </button>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}
      {aviso && <p className="text-sm text-emerald-700">{aviso}</p>}

      {pendientes.length > 0 && (
        <section className="rounded border border-amber-300 bg-amber-50 p-4 text-amber-800">
          <p className="font-semibold">
            El cierre anual exige los periodos intermedios cerrados
          </p>
          <p className="text-sm">
            Quedan {pendientes.length} periodo(s) sin cerrar:{" "}
            {pendientes
              .map((p) => (p.tipo === "MES" ? MESES[p.periodo - 1] : `T${p.periodo}`))
              .join(", ")}
          </p>
          <Link
            className="text-sm underline"
            href="/cierres/intermedio"
          >
            Ir al cierre intermedio
          </Link>
        </section>
      )}

      {cierre && (
        <section className="rounded border bg-white p-4 space-y-2">
          <h2 className="font-semibold">
            Ejercicio {cierre.ejercicio} · {cierre.estado}
          </h2>
          <dl className="grid grid-cols-1 gap-1 text-sm md:grid-cols-2">
            <div>
              <dt className="text-gray-500">Fecha de cierre</dt>
              <dd className="font-mono">{cierre.fecha_cierre}</dd>
            </div>
            <div>
              <dt className="text-gray-500">Resultado del ejercicio</dt>
              <dd className="font-mono">
                {formatearImporte(cierre.resultado_ejercicio)}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500">Asiento de regularizacion</dt>
              <dd className="font-mono text-xs">
                {cierre.asiento_regularizacion_id ?? "—"}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500">Asiento de cierre</dt>
              <dd className="font-mono text-xs">
                {cierre.asiento_cierre_id ?? "—"}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500">Asiento de apertura</dt>
              <dd className="font-mono text-xs">
                {cierre.asiento_apertura_id ?? "—"}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500">Cerrado por</dt>
              <dd className="text-xs">
                {cierre.cerrado_por ?? "—"} ·{" "}
                {cierre.cerrado_at.slice(0, 19)}
              </dd>
            </div>
          </dl>
        </section>
      )}

      {cargando ? (
        <p className="text-sm text-gray-500">Cargando…</p>
      ) : (
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b text-left text-gray-500">
              <th className="py-2 pr-3">Mes</th>
              <th className="py-2 pr-3">Rango</th>
              <th className="py-2">Estado</th>
            </tr>
          </thead>
          <tbody>
            {periodos.map((item) => (
              <tr key={item.periodo} className="border-b">
                <td className="py-1.5 pr-3">{MESES[item.periodo - 1]}</td>
                <td className="py-1.5 pr-3 font-mono text-xs">
                  {item.fecha_ini} → {item.fecha_fin}
                </td>
                <td className="py-1.5">{item.estado}</td>
              </tr>
            ))}
            {periodos.length === 0 && (
              <tr>
                <td colSpan={3} className="py-4 text-gray-500">
                  Todavia no hay periodos intermedios cerrados en {ejercicio}.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </main>
  );
}
