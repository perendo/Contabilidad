"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  Bloque,
  formatearImporte,
  formularEFE,
  InformeEFE,
  obtenerEFE,
} from "@/components/cashflow/api";

const BLOQUES: { clave: Bloque; etiqueta: string; descripcion: string }[] = [
  { clave: "operativa", etiqueta: "Operativa", descripcion: "Grupos 6/7 y tesorería" },
  { clave: "inversion", etiqueta: "Inversión", descripcion: "Grupo 2 (inmovilizado)" },
  { clave: "financiacion", etiqueta: "Financiación", descripcion: "Grupos 1/9 y deudas 16/17" },
];

export default function InformeEFEPage() {
  const anio = new Date().getFullYear();
  const [ejercicio, setEjercicio] = useState(anio);
  const [informe, setInforme] = useState<InformeEFE | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [formulando, setFormulando] = useState(false);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      setInforme(await obtenerEFE(ejercicio));
    } catch (err) {
      setInforme(null);
      setError(err instanceof Error ? err.message : "No se pudo cargar el EFE");
    } finally {
      setCargando(false);
    }
  }, [ejercicio]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const formular = async () => {
    if (!window.confirm("¿Formular el EFE? El informe quedará fijado y no admite cambios.")) {
      return;
    }
    setFormulando(true);
    setError(null);
    setAviso(null);
    try {
      const resultado = await formularEFE(ejercicio);
      setAviso(
        resultado.sin_conciliar
          ? "Formulado con aviso: el saldo no coincide con la conciliación bancaria."
          : `EFE formulado (${resultado.informe_id.slice(0, 8)}...).`
      );
      await cargar();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo formular el EFE");
    } finally {
      setFormulando(false);
    }
  };

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Estado de Flujos de Efectivo</h1>
          <p className="text-sm text-gray-500">
            Informe consolidado por tipo de actividad: apertura + movimientos = cierre
          </p>
        </div>
        <Link
          href="/tesoreria/previsiones"
          className="rounded border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
        >
          Previsión
        </Link>
      </div>

      <section className="flex items-end gap-3">
        <label className="text-sm">
          <span className="block font-medium text-gray-700">Ejercicio</span>
          <input
            type="number"
            value={ejercicio}
            onChange={(e) => setEjercicio(Number(e.target.value))}
            className="mt-1 w-32 rounded border px-2 py-1"
          />
        </label>
        <button
          onClick={cargar}
          className="rounded border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
        >
          Consultar
        </button>
        <button
          onClick={formular}
          disabled={formulando || cargando || informe?.formulado}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {informe?.formulado ? "Ya formulado" : formulando ? "Formulando…" : "Formular"}
        </button>
      </section>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 p-4 text-red-700">{error}</div>
      )}
      {aviso && (
        <div className="rounded border border-amber-300 bg-amber-50 p-4 text-amber-800">
          {aviso}
        </div>
      )}

      {cargando && <p className="text-sm text-gray-500">Cargando…</p>}

      {informe && (
        <>
          <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <div className="rounded border bg-white p-4">
              <div className="text-xs uppercase text-gray-500">Saldo inicial</div>
              <div className="font-mono text-xl">{formatearImporte(informe.saldo_inicial)}</div>
            </div>
            <div className="rounded border bg-white p-4">
              <div className="text-xs uppercase text-gray-500">Variación neta</div>
              <div className="font-mono text-xl">
                {formatearImporte(informe.variacion_neta)}
              </div>
            </div>
            <div className="rounded border bg-white p-4">
              <div className="text-xs uppercase text-gray-500">Saldo final</div>
              <div className="font-mono text-xl font-bold">
                {formatearImporte(informe.saldo_final)}
              </div>
            </div>
            <div className="rounded border bg-white p-4">
              <div className="text-xs uppercase text-gray-500">Cuadre</div>
              <div
                className={`text-xl font-bold ${
                  informe.cuadre ? "text-green-700" : "text-red-600"
                }`}
              >
                {informe.cuadre ? "Sí" : "No"}
              </div>
            </div>
          </section>

          {informe.sin_conciliar && (
            <div className="rounded border border-amber-300 bg-amber-50 p-4 text-amber-800">
              <p className="font-semibold">Diferencia con la conciliación bancaria</p>
              <p className="text-sm">
                Saldo del EFE {formatearImporte(informe.saldo_final)} frente a{" "}
                {formatearImporte(informe.saldo_conciliacion)} conciliado. Hay movimientos sin
                conciliar: el aviso no bloquea la formulación.
              </p>
            </div>
          )}

          {informe.formulado && (
            <div className="rounded border border-green-300 bg-green-50 p-4 text-green-800">
              Informe formulado{fmt(informe.informe_id)}. Es un documento inmutable.
            </div>
          )}

          {BLOQUES.map((bloque) => {
            const datos = informe.bloques[bloque.clave];
            return (
              <section key={bloque.clave} className="space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-lg font-semibold">{bloque.etiqueta}</h2>
                    <p className="text-xs text-gray-500">{bloque.descripcion}</p>
                  </div>
                  <span className="font-mono text-lg font-semibold">
                    {formatearImporte(datos.total)}
                  </span>
                </div>
                <div className="overflow-x-auto rounded border bg-white">
                  <table className="w-full text-left text-sm">
                    <thead className="border-b bg-gray-100 text-xs uppercase text-gray-600">
                      <tr>
                        <th className="p-3">Cuenta</th>
                        <th className="p-3">Clasificación</th>
                        <th className="p-3 text-right">Importe</th>
                      </tr>
                    </thead>
                    <tbody>
                      {datos.items.length === 0 ? (
                        <tr>
                          <td colSpan={3} className="p-4 text-center text-gray-400">
                            Sin movimientos en este bloque
                          </td>
                        </tr>
                      ) : (
                        datos.items.map((item) => (
                          <tr key={item.cuenta_id} className="border-b hover:bg-gray-50">
                            <td className="p-3 font-mono">{item.codigo_cuenta}</td>
                            <td className="p-3">
                              {item.override_usuario ? (
                                <span className="rounded bg-blue-100 px-1.5 py-0.5 text-xs text-blue-800">
                                  reclasificada
                                </span>
                              ) : (
                                <span className="text-xs text-gray-500">automática</span>
                              )}
                            </td>
                            <td className="p-3 text-right font-mono">
                              {formatearImporte(item.importe)}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </section>
            );
          })}
        </>
      )}
    </div>
  );
}

function fmt(informeId: string | null): string {
  return informeId ? ` (${informeId.slice(0, 8)}...)` : "";
}
