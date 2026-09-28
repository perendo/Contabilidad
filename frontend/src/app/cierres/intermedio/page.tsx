"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  cerrarPeriodo,
  ETIQUETA_ESTADO,
  formatearImporte,
  listarPeriodos,
  MESES,
  type EstadoPeriodo,
  type PeriodoCerrado,
  type ResultadoCierre,
  type TipoPeriodo,
} from "@/components/closing/api";

const EJERCICIO_POR_DEFECTO = new Date().getFullYear();

export default function CierreIntermedioPage() {
  const [ejercicio, setEjercicio] = useState(EJERCICIO_POR_DEFECTO);
  const [tipo, setTipo] = useState<TipoPeriodo>("MES");
  const [periodo, setPeriodo] = useState(1);
  const [items, setItems] = useState<PeriodoCerrado[]>([]);
  const [resultado, setResultado] = useState<ResultadoCierre | null>(null);
  const [cargando, setCargando] = useState(true);
  const [cerrando, setCerrando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      // Con `ejercicio` + `tipo` el backend devuelve el calendario completo: los
      // periodos sin fila estan `abierto` (research D2, sin tabla de calendario).
      const datos = await listarPeriodos({ ejercicio, tipo, page_size: 12 });
      setItems(datos.items);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "No se pudieron cargar los periodos");
    } finally {
      setCargando(false);
    }
  }, [ejercicio, tipo]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  async function cerrar() {
    const etiqueta = tipo === "MES" ? MESES[periodo - 1] : `Trimestre ${periodo}`;
    const ok = window.confirm(
      `¿Cerrar ${etiqueta} de ${ejercicio}?\n\n` +
        "Se generara un balance de comprobacion inmutable y el periodo quedara " +
        "bloqueado para nuevas contabilizaciones."
    );
    if (!ok) return;
    setCerrando(true);
    setError(null);
    setAviso(null);
    try {
      const creado = await cerrarPeriodo({ ejercicio, tipo, periodo });
      setResultado(creado);
      setAviso(
        `Periodo cerrado. Balance de ${creado.balanza.n_lineas} linea(s) ` +
          `con total ${creado.balanza.total_debe}.`
      );
      await cargar();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "No se pudo cerrar el periodo");
    } finally {
      setCerrando(false);
    }
  }

  const total = tipo === "MES" ? 12 : 4;
  const seleccionado = items.find((item) => item.periodo === periodo);

  return (
    <main className="p-6 max-w-6xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Cierre intermedio</h1>
          <p className="text-sm text-gray-500">
            Cierra un mes o un trimestre y registra su balance de comprobacion
          </p>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <Link className="text-blue-600 underline" href="/cierres">
            Cierres
          </Link>
          <Link className="text-blue-600 underline" href="/cierres/anual">
            Anual
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
          <span className="block text-gray-600 mb-1">Tipo</span>
          <select
            className="border rounded px-2 py-1"
            value={tipo}
            onChange={(e) => {
              setTipo(e.target.value as TipoPeriodo);
              setPeriodo(1);
            }}
          >
            <option value="MES">Mes</option>
            <option value="TRIMESTRE">Trimestre</option>
          </select>
        </label>
        <label className="text-sm">
          <span className="block text-gray-600 mb-1">Periodo</span>
          <select
            className="border rounded px-2 py-1"
            value={periodo}
            onChange={(e) => setPeriodo(Number(e.target.value))}
          >
            {Array.from({ length: total }, (_, indice) => indice + 1).map((numero) => (
              <option key={numero} value={numero}>
                {tipo === "MES" ? MESES[numero - 1] : `Trimestre ${numero}`}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={() => void cerrar()}
          disabled={cerrando || cargando || seleccionado?.estado !== "abierto"}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {cerrando ? "Cerrando…" : "Cerrar periodo"}
        </button>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}
      {aviso && <p className="text-sm text-emerald-700">{aviso}</p>}

      {resultado && (
        <section className="rounded border border-green-300 bg-green-50 p-4 text-green-800">
          <p className="font-semibold">
            {resultado.tipo} {resultado.periodo} de {resultado.ejercicio} cerrado
          </p>
          <p className="text-sm">
            Total debe {formatearImporte(resultado.balanza.total_debe)} · Total
            haber {formatearImporte(resultado.balanza.total_haber)} ·{" "}
            {resultado.balanza.cuadra ? "el balance cuadra" : "DESCUADRE"} ·
            Resultado provisional{" "}
            {formatearImporte(resultado.resultado_provisional)}
          </p>
          <p className="text-xs font-mono mt-1">
            Huella del snapshot: {resultado.balanza.sha256}
          </p>
        </section>
      )}

      {cargando ? (
        <p className="text-sm text-gray-500">Cargando periodos…</p>
      ) : (
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b text-left text-gray-500">
              <th className="py-2 pr-3">Periodo</th>
              <th className="py-2 pr-3">Rango</th>
              <th className="py-2 pr-3">Estado</th>
              <th className="py-2 pr-3">Reaperturas</th>
              <th className="py-2 pr-3">Cerrado</th>
              <th className="py-2">Balance</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.periodo} className="border-b hover:bg-gray-50">
                <td className="py-1.5 pr-3">
                  {item.tipo === "MES"
                    ? MESES[item.periodo - 1]
                    : `Trimestre ${item.periodo}`}
                </td>
                <td className="py-1.5 pr-3 font-mono text-xs">
                  {item.fecha_ini} → {item.fecha_fin}
                </td>
                <td className="py-1.5 pr-3">
                  <span
                    className={`rounded px-2 py-0.5 text-xs ${
                      item.estado === "abierto"
                        ? "bg-gray-100 text-gray-700"
                        : item.estado === "cerrado"
                          ? "bg-blue-100 text-blue-800"
                          : "bg-amber-100 text-amber-800"
                    }`}
                  >
                    {ETIQUETA_ESTADO[item.estado as EstadoPeriodo]}
                  </span>
                </td>
                <td className="py-1.5 pr-3">{item.n_reaperturas}</td>
                <td className="py-1.5 pr-3 text-xs text-gray-500">
                  {item.cerrado_at ? item.cerrado_at.slice(0, 19) : "—"}
                </td>
                <td className="py-1.5">
                  {item.periodo_id ? (
                    <Link
                      className="text-blue-600 underline"
                      href={`/cierres/${item.periodo_id}`}
                    >
                      Ver balance
                    </Link>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
