"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";

import {
  ApiError,
  aprobarReapertura,
  ETIQUETA_ESTADO,
  ETIQUETA_SOLICITUD,
  obtenerBalanza,
  obtenerReapertura,
  rechazarReapertura,
  rectificarReapertura,
  type Balanza,
  type DetalleSolicitud,
} from "@/components/closing/api";
import BalanzaTabla from "@/components/closing/BalanzaTabla";

/**
 * Detalle de un periodo cerrado (su balance) o de una solicitud de reapertura.
 * La ruta es compartida: se intenta primero el balance y, si no existe, la
 * solicitud; ambas devuelven 404 desde la API si el recurso no es de la
 * empresa activa (constitucion III).
 */
export default function CierreDetallePage() {
  const params = useParams<{ id: string }>();
  const id = params.id;

  const [balanza, setBalanza] = useState<Balanza | null>(null);
  const [solicitud, setSolicitud] = useState<DetalleSolicitud | null>(null);
  const [asientoId, setAsientoId] = useState("");
  const [cargando, setCargando] = useState(true);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mensaje, setMensaje] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      try {
        setBalanza(await obtenerBalanza(id));
        setSolicitud(null);
      } catch (e) {
        if (!(e instanceof ApiError) || e.status !== 404) throw e;
        try {
          setSolicitud(await obtenerReapertura(id));
          setBalanza(null);
        } catch (e2) {
          if (e2 instanceof ApiError && e2.status === 404) {
            setBalanza(null);
            setSolicitud(null);
            setError("El recurso no existe en la empresa activa.");
            return;
          }
          throw e2;
        }
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "No se pudo cargar el detalle");
    } finally {
      setCargando(false);
    }
  }, [id]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  async function ejecutar(fn: () => Promise<unknown>, ok: string) {
    setOcupado(true);
    setError(null);
    setMensaje(null);
    try {
      await fn();
      setMensaje(ok);
      await cargar();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error en la operacion");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <main className="p-6 max-w-5xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Detalle del cierre</h1>
        <Link className="text-sm text-blue-600 underline" href="/cierres">
          Cierres
        </Link>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}
      {mensaje && <p className="text-sm text-emerald-700">{mensaje}</p>}
      {cargando && <p className="text-sm text-gray-500">Cargando…</p>}

      {balanza && (
        <section className="space-y-3">
          <div className="rounded border bg-white p-4 text-sm">
            <p className="font-semibold">
              Balance de comprobacion del {balanza.fecha_ini} a {balanza.fecha_fin}
            </p>
            <p className="text-gray-600">
              Generado el {balanza.fecha_generacion.slice(0, 19)} ·{" "}
              {balanza.n_lineas} linea(s) ·{" "}
              {balanza.cuadra ? "el balance cuadra" : "DESCUADRE"}
            </p>
            <p className="mt-1 font-mono text-xs text-gray-500">
              Huella: {balanza.sha256}
            </p>
          </div>
          <BalanzaTabla
            lineas={balanza.lineas}
            totalDebe={balanza.total_debe}
            totalHaber={balanza.total_haber}
            resultadoProvisional={balanza.resultado_provisional}
          />
          <p className="text-xs text-gray-500">
            El balance es un snapshot inmutable: no admite cambios. Para corregirlo
            hay que reabrir el periodo y registrar un asiento rectificativo.
          </p>
        </section>
      )}

      {solicitud && (
        <section className="space-y-4">
          <div className="rounded border bg-white p-4 space-y-1 text-sm">
            <h2 className="font-semibold">
              Solicitud {solicitud.numero_solicitud} ·{" "}
              {ETIQUETA_SOLICITUD[solicitud.estado]}
            </h2>
            <p className="text-gray-700">{solicitud.motivo}</p>
            {solicitud.nota_impacto && (
              <p className="text-xs text-amber-700">
                Impacto declarado: {solicitud.nota_impacto}
              </p>
            )}
            <p className="text-xs text-gray-500">
              Solicitada por {solicitud.usuario_solicitante ?? "—"} el{" "}
              {solicitud.fecha_solicitud.slice(0, 19)}
              {solicitud.aprobada_por
                ? ` · aprobada por ${solicitud.aprobada_por} el ${solicitud.fecha_aprobacion?.slice(0, 19)}`
                : ""}
            </p>
            {solicitud.asiento_rectificacion_id && (
              <p className="font-mono text-xs">
                Asiento rectificativo: {solicitud.asiento_rectificacion_id}
              </p>
            )}
          </div>

          {solicitud.periodo_cerrado && (
            <div className="rounded border bg-gray-50 p-3 text-sm">
              Periodo {solicitud.periodo_cerrado.tipo}{" "}
              {solicitud.periodo_cerrado.periodo} (
              {solicitud.periodo_cerrado.fecha_ini} →{" "}
              {solicitud.periodo_cerrado.fecha_fin}):{" "}
              <span className="font-semibold">
                {ETIQUETA_ESTADO[solicitud.periodo_cerrado.estado]}
              </span>{" "}
              · {solicitud.periodo_cerrado.n_reaperturas} reapertura(s)
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            {solicitud.estado === "pendiente" && (
              <>
                <button
                  disabled={ocupado}
                  onClick={() =>
                    void ejecutar(
                      () => aprobarReapertura(solicitud.solicitud_id),
                      "Solicitud aprobada: el periodo queda abierto al ajuste."
                    )
                  }
                  className="rounded bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  Aprobar
                </button>
                <button
                  disabled={ocupado}
                  onClick={() =>
                    void ejecutar(
                      () => rechazarReapertura(solicitud.solicitud_id),
                      "Solicitud rechazada: el periodo sigue bloqueado."
                    )
                  }
                  className="rounded border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                >
                  Rechazar
                </button>
              </>
            )}

            {solicitud.estado === "reabierta" && (
              <div className="flex flex-wrap items-end gap-2">
                <label className="text-sm">
                  <span className="block text-gray-600 mb-1">
                    Asiento ADJUSTMENT/REVERSAL (UUID)
                  </span>
                  <input
                    className="border rounded px-2 py-1 font-mono text-sm"
                    value={asientoId}
                    onChange={(e) => setAsientoId(e.target.value)}
                  />
                </label>
                <button
                  disabled={ocupado || asientoId.trim().length === 0}
                  onClick={() =>
                    void ejecutar(
                      () =>
                        rectificarReapertura(
                          solicitud.solicitud_id,
                          asientoId.trim()
                        ),
                      "Ajuste registrado: el periodo vuelve a quedar bloqueado."
                    )
                  }
                  className="rounded bg-emerald-600 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
                >
                  Registrar rectificacion
                </button>
              </div>
            )}
          </div>

          {solicitud.fecha_cierre_efectivo && (
            <p className="text-sm text-gray-600">
              Re-cierre efectivo el {solicitud.fecha_cierre_efectivo.slice(0, 19)}
            </p>
          )}
        </section>
      )}
    </main>
  );
}
