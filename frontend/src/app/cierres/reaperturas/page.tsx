"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import {
  ApiError,
  aprobarReapertura,
  ETIQUETA_SOLICITUD,
  listarReaperturas,
  listarPeriodos,
  MESES,
  rechazarReapertura,
  rectificarReapertura,
  solicitarReapertura,
  type DetalleSolicitud,
  type EstadoSolicitud,
  type PeriodoCerrado,
  type SolicitudReapertura,
  type TipoPeriodoReapertura,
} from "@/components/closing/api";

const EJERCICIO_POR_DEFECTO = new Date().getFullYear();

const ESTADOS: { valor: EstadoSolicitud | ""; etiqueta: string }[] = [
  { valor: "", etiqueta: "Todas" },
  { valor: "pendiente", etiqueta: "Pendientes" },
  { valor: "reabierta", etiqueta: "Reabiertas" },
  { valor: "cerrada", etiqueta: "Cerradas" },
  { valor: "rechazada", etiqueta: "Rechazadas" },
];

export default function ReaperturasPage() {
  const [ejercicio, setEjercicio] = useState(EJERCICIO_POR_DEFECTO);
  const [tipoPeriodo, setTipoPeriodo] = useState<TipoPeriodoReapertura>("MES");
  const [periodo, setPeriodo] = useState(1);
  const [motivo, setMotivo] = useState("");
  const [notaImpacto, setNotaImpacto] = useState("");
  const [estado, setEstado] = useState<EstadoSolicitud | "">("");

  const [items, setItems] = useState<SolicitudReapertura[]>([]);
  const [total, setTotal] = useState(0);
  const [cerrados, setCerrados] = useState<PeriodoCerrado[]>([]);
  const [cargando, setCargando] = useState(true);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mensaje, setMensaje] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const [solicitudes, periodos] = await Promise.all([
        listarReaperturas({ ejercicio, estado: estado || undefined, page_size: 100 }),
        listarPeriodos({ ejercicio, tipo: "MES", page_size: 12 }),
      ]);
      setItems(solicitudes.items);
      setTotal(solicitudes.total);
      setCerrados(periodos.items);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error al listar las reaperturas");
    } finally {
      setCargando(false);
    }
  }, [ejercicio, estado]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  async function enviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    setEnviando(true);
    setError(null);
    setMensaje(null);
    try {
      const creada = await solicitarReapertura({
        ejercicio,
        tipo_periodo: tipoPeriodo,
        periodo: tipoPeriodo === "ANUAL" ? null : periodo,
        motivo,
        nota_impacto: notaImpacto || null,
      });
      setMotivo("");
      setNotaImpacto("");
      setMensaje(
        `Solicitud ${creada.numero_solicitud} registrada (${ETIQUETA_SOLICITUD[creada.estado]}).`
      );
      await cargar();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error al solicitar la reapertura");
    } finally {
      setEnviando(false);
    }
  }

  async function accion(
    fn: () => Promise<{ estado: EstadoSolicitud }>,
    mensajeOk: string
  ) {
    setError(null);
    setMensaje(null);
    try {
      const resultado = await fn();
      setMensaje(`${mensajeOk} (${ETIQUETA_SOLICITUD[resultado.estado]}).`);
      await cargar();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error en la accion de reapertura");
    }
  }

  const cerradosDisponibles = cerrados.filter(
    (p) => p.periodo_id !== null && p.estado !== "abierto"
  );

  return (
    <main className="p-6 max-w-6xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Reaperturas controladas</h1>
          <p className="text-sm text-gray-500">
            Justificacion, aprobacion y asiento rectificativo que preserva la
            inmutabilidad del diario
          </p>
        </div>
        <Link className="text-sm text-blue-600 underline" href="/cierres">
          Cierres
        </Link>
      </div>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 p-3 text-red-700">
          {error}
        </div>
      )}
      {mensaje && (
        <div className="rounded border border-green-200 bg-green-50 p-3 text-green-700">
          {mensaje}
        </div>
      )}

      <form
        onSubmit={enviar}
        className="rounded border bg-gray-50 p-4 space-y-3"
      >
        <h2 className="font-semibold">Nueva solicitud de reapertura</h2>
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
            <span className="block text-gray-600 mb-1">Tipo de periodo</span>
            <select
              className="border rounded px-2 py-1"
              value={tipoPeriodo}
              onChange={(e) =>
                setTipoPeriodo(e.target.value as TipoPeriodoReapertura)
              }
            >
              <option value="MES">Mes</option>
              <option value="TRIMESTRE">Trimestre</option>
              <option value="ANUAL">Ejercicio completo</option>
            </select>
          </label>
          {tipoPeriodo !== "ANUAL" && (
            <label className="text-sm">
              <span className="block text-gray-600 mb-1">Periodo</span>
              <select
                className="border rounded px-2 py-1"
                value={periodo}
                onChange={(e) => setPeriodo(Number(e.target.value))}
              >
                {Array.from({ length: 12 }, (_, i) => i + 1).map((numero) => (
                  <option key={numero} value={numero}>
                    {MESES[numero - 1]}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
        <label className="block text-sm">
          <span className="block text-gray-600 mb-1">
            Motivo (obligatorio, FR-006)
          </span>
          <textarea
            required
            className="border rounded p-2 w-full"
            rows={2}
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            placeholder="Error de imputacion detectado en el asiento n.º 3"
          />
        </label>
        <label className="block text-sm">
          <span className="block text-gray-600 mb-1">
            Nota de impacto (obligatoria si el IS ya esta contabilizado)
          </span>
          <textarea
            className="border rounded p-2 w-full"
            rows={2}
            value={notaImpacto}
            onChange={(e) => setNotaImpacto(e.target.value)}
          />
        </label>
        <button
          type="submit"
          disabled={enviando}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {enviando ? "Enviando…" : "Solicitar reapertura"}
        </button>
      </form>

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
        <span className="text-sm text-gray-500">{total} solicitudes</span>
      </section>

      {cargando ? (
        <p className="text-sm text-gray-500">Cargando…</p>
      ) : (
        <div className="overflow-x-auto rounded border bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b bg-gray-50 text-xs uppercase text-gray-600">
              <tr>
                <th className="p-3">Nº</th>
                <th className="p-3">Periodo</th>
                <th className="p-3">Motivo</th>
                <th className="p-3">Estado</th>
                <th className="p-3">Asiento rectificativo</th>
                <th className="p-3">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <FilaSolicitud
                  key={item.solicitud_id}
                  solicitud={item}
                  cerradaDisponibles={cerradosDisponibles}
                  onAccion={accion}
                />
              ))}
              {items.length === 0 && (
                <tr>
                  <td colSpan={6} className="p-6 text-center text-gray-400">
                    No hay solicitudes para los filtros seleccionados
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}

function FilaSolicitud({
  solicitud,
  cerradaDisponibles,
  onAccion,
}: {
  solicitud: SolicitudReapertura;
  cerradaDisponibles: PeriodoCerrado[];
  onAccion: (
    fn: () => Promise<{ estado: EstadoSolicitud }>,
    mensajeOk: string
  ) => Promise<void>;
}) {
  const [asientoId, setAsientoId] = useState("");

  return (
    <tr className="border-b hover:bg-gray-50 align-top">
      <td className="p-3 font-mono">{solicitud.numero_solicitud}</td>
      <td className="p-3">
        {solicitud.tipo_periodo === "MES"
          ? MESES[(solicitud.periodo ?? 1) - 1]
          : solicitud.tipo_periodo === "TRIMESTRE"
            ? `Trimestre ${solicitud.periodo}`
            : "Ejercicio completo"}
        <div className="text-xs text-gray-500">{solicitud.ejercicio}</div>
      </td>
      <td className="p-3 max-w-xs">
        <p>{solicitud.motivo}</p>
        {solicitud.nota_impacto && (
          <p className="mt-1 text-xs text-amber-700">
            Impacto: {solicitud.nota_impacto}
          </p>
        )}
      </td>
      <td className="p-3">
        <span
          className={`rounded px-2 py-0.5 text-xs ${
            solicitud.estado === "cerrada"
              ? "bg-green-100 text-green-800"
              : solicitud.estado === "rechazada"
                ? "bg-gray-200 text-gray-700"
                : solicitud.estado === "pendiente"
                  ? "bg-amber-100 text-amber-800"
                  : "bg-blue-100 text-blue-800"
          }`}
        >
          {ETIQUETA_SOLICITUD[solicitud.estado]}
        </span>
        <div className="mt-1 text-xs text-gray-500">
          {solicitud.usuario_solicitante ?? "—"} ·{" "}
          {solicitud.fecha_solicitud.slice(0, 10)}
        </div>
      </td>
      <td className="p-3 font-mono text-xs">
        {solicitud.asiento_rectificacion_id
          ? solicitud.asiento_rectificacion_id.slice(0, 8)
          : "—"}
      </td>
      <td className="p-3">
        <div className="flex flex-wrap items-center gap-2">
          {solicitud.estado === "pendiente" && (
            <>
              <button
                onClick={() =>
                  void onAccion(
                    () => aprobarReapertura(solicitud.solicitud_id),
                    "Solicitud aprobada; el periodo queda abierto al ajuste"
                  )
                }
                className="rounded border border-gray-300 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50"
              >
                Aprobar
              </button>
              <button
                onClick={() =>
                  void onAccion(
                    () => rechazarReapertura(solicitud.solicitud_id),
                    "Solicitud rechazada"
                  )
                }
                className="rounded border border-gray-300 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50"
              >
                Rechazar
              </button>
            </>
          )}
          {solicitud.estado === "reabierta" && (
            <Rectificar
              solicitud={solicitud}
              asientoId={asientoId}
              onAsientoId={setAsientoId}
              cerradaDisponibles={cerradaDisponibles}
              onAccion={onAccion}
            />
          )}
          <Link
            className="text-xs text-blue-600 underline"
            href={`/cierres/${solicitud.solicitud_id}`}
          >
            Detalle
          </Link>
        </div>
      </td>
    </tr>
  );
}

function Rectificar({
  solicitud,
  asientoId,
  onAsientoId,
  cerradaDisponibles,
  onAccion,
}: {
  solicitud: SolicitudReapertura;
  asientoId: string;
  onAsientoId: (valor: string) => void;
  cerradaDisponibles: PeriodoCerrado[];
  onAccion: (
    fn: () => Promise<{ estado: EstadoSolicitud }>,
    mensajeOk: string
  ) => Promise<void>;
}) {
  return (
    <div className="space-y-1">
      <input
        className="w-44 border rounded px-2 py-1 font-mono text-xs"
        placeholder="UUID del asiento ADJUSTMENT"
        value={asientoId}
        onChange={(e) => onAsientoId(e.target.value)}
      />
      <button
        onClick={() =>
          void onAccion(
            () => rectificarReapertura(solicitud.solicitud_id, asientoId.trim()),
            "Ajuste registrado; el periodo vuelve a quedar bloqueado"
          )
        }
        disabled={asientoId.trim().length === 0}
        className="rounded bg-emerald-600 px-2 py-1 text-xs font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
      >
        Registrar rectificacion
      </button>
      {cerradaDisponibles.length > 0 && (
        <p className="text-xs text-gray-500">
          El asiento debe ser ADJUSTMENT o REVERSAL y tener fecha dentro de{" "}
          {solicitud.periodo !== null
            ? MESES[solicitud.periodo - 1]
            : "el periodo"}{" "}
          reabierto.
        </p>
      )}
    </div>
  );
}

export type { DetalleSolicitud };
