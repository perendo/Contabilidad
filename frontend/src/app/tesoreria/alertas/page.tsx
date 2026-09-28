"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  atenderAlerta,
  Alerta,
  EstadoAlerta,
  formatearImporte,
  ignorarAlerta,
  listarAlertas,
} from "@/components/cashflow/api";

const ESTADOS: { valor: EstadoAlerta | ""; etiqueta: string }[] = [
  { valor: "", etiqueta: "Todas" },
  { valor: "abierta", etiqueta: "Abiertas" },
  { valor: "atendida", etiqueta: "Atendidas" },
  { valor: "ignorada", etiqueta: "Ignoradas" },
];

export default function AlertasLiquidezPage() {
  const [items, setItems] = useState<Alerta[]>([]);
  const [total, setTotal] = useState(0);
  const [estado, setEstado] = useState<EstadoAlerta | "">("abierta");
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mensaje, setMensaje] = useState<string | null>(null);
  const [ocupada, setOcupada] = useState<string | null>(null);
  const [nuevasFechas, setNuevasFechas] = useState<Record<string, string>>({});

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const respuesta = await listarAlertas(estado ? { estado } : {});
      setItems(respuesta.items);
      setTotal(respuesta.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudieron cargar las alertas");
    } finally {
      setCargando(false);
    }
  }, [estado]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const reprogramar = async (alerta: Alerta) => {
    const nueva = nuevasFechas[alerta.id] ?? "";
    if (!nueva) {
      setError("Indica la nueva fecha prevista del pago");
      return;
    }
    setOcupada(alerta.id);
    setError(null);
    setMensaje(null);
    try {
      await atenderAlerta(alerta.id, {
        accion: "reprogramar_pago",
        movimiento_id: alerta.movimiento_origen_id,
        nueva_fecha: nueva,
      });
      setMensaje(`Alerta del ${alerta.fecha} atendida: pago reprogramado al ${nueva}.`);
      await cargar();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo reprogramar el pago");
    } finally {
      setOcupada(null);
    }
  };

  const incluirIngreso = async (alerta: Alerta) => {
    if (
      !window.confirm(
        `¿Crear un ingreso previsto de ${formatearImporte(alerta.importe_deficit)} el ${alerta.fecha}?`
      )
    ) {
      return;
    }
    setOcupada(alerta.id);
    setError(null);
    setMensaje(null);
    try {
      await atenderAlerta(alerta.id, { accion: "incluir_ingreso" });
      setMensaje(`Alerta del ${alerta.fecha} atendida: ingreso previsto por el déficit.`);
      await cargar();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo incluir el ingreso");
    } finally {
      setOcupada(null);
    }
  };

  const ignorar = async (alerta: Alerta) => {
    if (!window.confirm(`¿Desestimar la alerta del ${alerta.fecha}?`)) return;
    setOcupada(alerta.id);
    setError(null);
    setMensaje(null);
    try {
      await ignorarAlerta(alerta.id);
      setMensaje(`Alerta del ${alerta.fecha} desestimada.`);
      await cargar();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo ignorar la alerta");
    } finally {
      setOcupada(null);
    }
  };

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Alertas de Liquidez</h1>
          <p className="text-sm text-gray-500">
            Periodos con saldo proyectado negativo: reprograma un pago o incorpora un ingreso
          </p>
        </div>
        <Link
          href="/tesoreria/previsiones"
          className="rounded border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
        >
          Previsión
        </Link>
      </div>

      <section className="flex items-center justify-between">
        <div className="flex space-x-1">
          {ESTADOS.map((opcion) => (
            <button
              key={opcion.valor || "todas"}
              onClick={() => setEstado(opcion.valor)}
              className={`rounded px-3 py-1.5 text-sm ${
                estado === opcion.valor
                  ? "bg-blue-600 text-white"
                  : "border border-gray-300 text-gray-700 hover:bg-gray-50"
              }`}
            >
              {opcion.etiqueta}
            </button>
          ))}
        </div>
        <span className="text-sm text-gray-500">{total} alertas</span>
      </section>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 p-4 text-red-700">{error}</div>
      )}
      {mensaje && (
        <div className="rounded border border-green-300 bg-green-50 p-4 text-green-800">
          {mensaje}
        </div>
      )}

      {cargando ? (
        <div className="p-8 text-center text-gray-500">Cargando alertas…</div>
      ) : items.length === 0 ? (
        <div className="rounded border bg-white p-6 text-center text-gray-400">
          No hay alertas de liquidez en este estado
        </div>
      ) : (
        <div className="space-y-4">
          {items.map((alerta) => (
            <div
              key={alerta.id}
              className={`rounded border p-5 ${
                alerta.estado === "abierta" ? "border-red-200 bg-red-50" : "bg-white"
              }`}
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-xs uppercase text-gray-500">Periodo {alerta.fecha}</div>
                  <div className="mt-1 font-mono text-2xl font-bold text-red-700">
                    {formatearImporte(alerta.saldo_proyectado)}
                  </div>
                  <div className="text-sm text-gray-600">
                    Déficit: {formatearImporte(alerta.importe_deficit)} · Acción sugerida:{" "}
                    {alerta.accion_sugerida === "reprogramar_pago"
                      ? "reprogramar un pago"
                      : "incluir un ingreso previsto"}
                  </div>
                </div>
                <span
                  className={`rounded px-2 py-1 text-xs font-semibold ${
                    alerta.estado === "abierta"
                      ? "bg-red-600 text-white"
                      : alerta.estado === "atendida"
                        ? "bg-green-600 text-white"
                        : "bg-gray-400 text-white"
                  }`}
                >
                  {alerta.estado}
                </span>
              </div>

              {alerta.estado === "abierta" && (
                <div className="mt-4 flex flex-wrap items-end gap-3">
                  {alerta.movimiento_origen_id && (
                    <>
                      <label className="text-sm">
                        <span className="block font-medium text-gray-700">
                          Nueva fecha del pago
                        </span>
                        <input
                          type="date"
                          value={nuevasFechas[alerta.id] ?? ""}
                          onChange={(e) =>
                            setNuevasFechas((previo) => ({
                              ...previo,
                              [alerta.id]: e.target.value,
                            }))
                          }
                          className="mt-1 rounded border px-2 py-1"
                        />
                      </label>
                      <button
                        onClick={() => reprogramar(alerta)}
                        disabled={ocupada === alerta.id}
                        className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
                      >
                        Reprogramar pago
                      </button>
                    </>
                  )}
                  <button
                    onClick={() => incluirIngreso(alerta)}
                    disabled={ocupada === alerta.id}
                    className="rounded border border-green-700 px-4 py-2 text-sm font-semibold text-green-700 hover:bg-green-50 disabled:opacity-50"
                  >
                    Incluir ingreso previsto
                  </button>
                  <button
                    onClick={() => ignorar(alerta)}
                    disabled={ocupada === alerta.id}
                    className="rounded border border-gray-400 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-50"
                  >
                    Desestimar
                  </button>
                </div>
              )}

              {alerta.estado === "atendida" && alerta.movimiento_origen_id && (
                <Link
                  href="/tesoreria/previsiones"
                  className="mt-3 inline-block text-sm text-blue-600 hover:underline"
                >
                  Regeneriza la previsión para ver el nuevo saldo →
                </Link>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
