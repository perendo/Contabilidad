"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  cuentasPresupuestables,
  guardarPresupuesto,
  importarPresupuesto,
  listarPresupuestos,
  periodoActual,
  type CuentaOption,
  type LineaPresupuesto,
  type Periodo,
  type TipoPresupuesto,
} from "@/components/budget/api";
import CentroSelect from "@/components/costcenters/CentroSelect";

const EJERCICIO_POR_DEFECTO = new Date().getFullYear();

export default function PresupuestosPage() {
  const [ejercicio, setEjercicio] = useState(EJERCICIO_POR_DEFECTO);
  const [items, setItems] = useState<LineaPresupuesto[]>([]);
  const [total, setTotal] = useState(0);
  const [cuentas, setCuentas] = useState<CuentaOption[]>([]);
  const [periodo, setPeriodo] = useState<Periodo | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const [cuentaId, setCuentaId] = useState("");
  const [centro, setCentro] = useState("");
  const [importe, setImporte] = useState("");
  const [observaciones, setObservaciones] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [filtroCuenta, setFiltroCuenta] = useState("");
  const [filtroCentro, setFiltroCentro] = useState("");
  const [filtroTexto, setFiltroTexto] = useState("");

  const recargar = useCallback(async (anio: number) => {
    setCargando(true);
    setError(null);
    try {
      const [listado, periodoActual_, disponibles] = await Promise.all([
        listarPresupuestos({ ejercicio: anio, page_size: 200 }),
        periodoActual(anio),
        cuentasPresupuestables(),
      ]);
      setItems(listado.items);
      setTotal(listado.total);
      setPeriodo(periodoActual_);
      setCuentas(disponibles);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error de conexion");
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    void recargar(ejercicio);
  }, [ejercicio, recargar]);

  const visibles = useMemo(() => {
    const texto = filtroTexto.trim().toLowerCase();
    return items.filter((linea) => {
      if (filtroCuenta && linea.codigo_cuenta !== filtroCuenta) return false;
      if (filtroCentro === "__sin__" && linea.centro_coste_id) return false;
      if (filtroCentro === "__con__" && !linea.centro_coste_id) return false;
      if (
        texto &&
        !linea.codigo_cuenta.toLowerCase().includes(texto) &&
        !linea.nombre_cuenta.toLowerCase().includes(texto)
      ) {
        return false;
      }
      return true;
    });
  }, [items, filtroCuenta, filtroCentro, filtroTexto]);

  const totalImportes = useMemo(
    () =>
      visibles.reduce(
        (suma, linea) => suma + Number(linea.importe),
        Number(0)
      ),
    [visibles]
  );

  async function enviar() {
    setError(null);
    setAviso(null);
    if (!cuentaId) {
      setError("Selecciona una cuenta del plan.");
      return;
    }
    const cuenta = cuentas.find((c) => String(c.account_id) === cuentaId);
    setEnviando(true);
    try {
      const guardada = await guardarPresupuesto({
        ejercicio,
        cuenta_id: Number(cuentaId),
        centro_coste_id: centro || null,
        importe,
        tipo: (cuenta?.codigo.startsWith("7")
          ? "ingreso"
          : "gasto") as TipoPresupuesto,
        observaciones: observaciones || undefined,
      });
      setAviso(
        `Presupuesto de ${guardada.codigo_cuenta ?? cuenta?.codigo ?? ""} guardado: ${guardada.importe}`
      );
      setImporte("");
      setObservaciones("");
      await recargar(ejercicio);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error de conexion");
    } finally {
      setEnviando(false);
    }
  }

  async function subir(e: React.ChangeEvent<HTMLInputElement>) {
    const fichero = e.target.files?.[0];
    if (!fichero) return;
    setError(null);
    setAviso(null);
    try {
      const resultado = await importarPresupuesto(fichero);
      if (resultado.errores.length > 0) {
        setError(
          `${resultado.errores.length} fila(s) invalida(s): ${resultado.errores
            .map((x) => `fila ${x.fila} — ${x.motivo}`)
            .join("; ")}`
        );
      } else {
        setAviso(`${resultado.importadas} linea(s) importadas.`);
      }
      await recargar(ejercicio);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Error de conexion");
    } finally {
      e.target.value = "";
    }
  }

  const bloqueado = periodo?.estado === "cerrado";

  return (
    <main className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Presupuesto anual</h1>
        <div className="flex items-center gap-3">
          <label className="text-sm text-gray-600" htmlFor="ejercicio">
            Ejercicio
          </label>
          <input
            id="ejercicio"
            type="number"
            className="border rounded px-2 py-1 text-sm w-24"
            value={ejercicio}
            onChange={(e) => setEjercicio(Number(e.target.value))}
          />
          <Link
            className="text-sm text-blue-600 underline"
            href="/presupuestos/seguimiento"
          >
            Seguimiento
          </Link>
          <Link
            className="text-sm text-blue-600 underline"
            href="/presupuestos/informes"
          >
            Informes
          </Link>
        </div>
      </div>

      <p className="text-sm text-gray-600">
        Periodo de seguimiento:{" "}
        {periodo
          ? `${periodo.numero_periodo} (${periodo.estado}) ${
              periodo.fecha_inicio
            } → ${periodo.fecha_fin}`
          : "sin periodo (se creara al guardar)"}
      </p>

      {bloqueado && (
        <p className="rounded bg-amber-100 text-amber-900 px-3 py-2 text-sm">
          El periodo {periodo?.numero_periodo} esta cerrado: el presupuesto queda
          bloqueado. Abre un periodo nuevo para volver a modificarlo.
        </p>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}
      {aviso && <p className="text-sm text-emerald-700">{aviso}</p>}

      <section className="rounded border p-4 space-y-3">
        <h2 className="font-medium">Alta o actualizacion por cuenta y centro</h2>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm">
            <span className="block text-gray-600 mb-1">Cuenta</span>
            <select
              className="border rounded px-2 py-1 w-80"
              value={cuentaId}
              onChange={(e) => setCuentaId(e.target.value)}
            >
              <option value="">— cuenta —</option>
              {cuentas.map((c) => (
                <option key={c.account_id} value={c.account_id}>
                  {c.codigo} · {c.nombre}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="block text-gray-600 mb-1">Centro de coste</span>
            <CentroSelect value={centro} onChange={setCentro} />
          </label>
          <label className="text-sm">
            <span className="block text-gray-600 mb-1">Importe anual</span>
            <input
              className="border rounded px-2 py-1 w-36"
              placeholder="48000.0000"
              value={importe}
              onChange={(e) => setImporte(e.target.value)}
            />
          </label>
          <label className="text-sm">
            <span className="block text-gray-600 mb-1">Observaciones</span>
            <input
              className="border rounded px-2 py-1 w-56"
              value={observaciones}
              onChange={(e) => setObservaciones(e.target.value)}
            />
          </label>
          <button
            type="button"
            onClick={() => void enviar()}
            disabled={enviando || bloqueado}
            className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
          >
            Guardar
          </button>
          <label className="text-sm">
            <span className="block text-gray-600 mb-1">Importar CSV</span>
            <input
              type="file"
              accept=".csv,text/csv,application/json"
              onChange={(e) => void subir(e)}
              className="text-sm"
            />
          </label>
        </div>
        <p className="text-xs text-gray-500">
          CSV: <code>codigo_cuenta,centro,importe,tipo</code>. El ejercicio se
          deduce del nombre del fichero (p. ej. <code>presupuesto_2026.csv</code>).
        </p>
      </section>

      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="font-medium">Lineas del ejercicio {ejercicio}</h2>
          <div className="flex items-center gap-2">
            <input
              className="border rounded px-2 py-1 text-sm"
              placeholder="Buscar cuenta"
              value={filtroTexto}
              onChange={(e) => setFiltroTexto(e.target.value)}
            />
            <select
              className="border rounded px-2 py-1 text-sm"
              value={filtroCuenta}
              onChange={(e) => setFiltroCuenta(e.target.value)}
            >
              <option value="">Todas las cuentas</option>
              {cuentas.map((c) => (
                <option key={c.account_id} value={c.codigo}>
                  {c.codigo}
                </option>
              ))}
            </select>
            <select
              className="border rounded px-2 py-1 text-sm"
              value={filtroCentro}
              onChange={(e) => setFiltroCentro(e.target.value)}
            >
              <option value="">Con y sin centro</option>
              <option value="__con__">Solo con centro</option>
              <option value="__sin__">Solo sin centro</option>
            </select>
          </div>
        </div>

        {cargando ? (
          <p className="text-sm text-gray-500">Cargando…</p>
        ) : (
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b text-left text-gray-500">
                <th className="py-2 pr-3">Cuenta</th>
                <th className="py-2 pr-3">Nombre</th>
                <th className="py-2 pr-3">Centro</th>
                <th className="py-2 pr-3 text-right">Importe</th>
                <th className="py-2">Tipo</th>
              </tr>
            </thead>
            <tbody>
              {visibles.map((linea) => (
                <tr key={linea.id} className="border-b hover:bg-gray-50">
                  <td className="py-1.5 pr-3 font-mono">{linea.codigo_cuenta}</td>
                  <td className="py-1.5 pr-3">{linea.nombre_cuenta}</td>
                  <td className="py-1.5 pr-3">
                    {linea.nombre_centro ?? "— sin centro —"}
                  </td>
                  <td className="py-1.5 pr-3 text-right font-mono">
                    {linea.importe}
                  </td>
                  <td className="py-1.5">{linea.tipo}</td>
                </tr>
              ))}
              {visibles.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-4 text-gray-500">
                    No hay lineas de presupuesto para este ejercicio.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
        <p className="text-xs text-gray-500">
          {visibles.length} de {total} linea(s) · suma visible{" "}
          {totalImportes.toFixed(4)}
        </p>
      </section>
    </main>
  );
}
