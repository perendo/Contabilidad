"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  obtenerCesion,
  DetalleCesion,
  MedioNotificacion,
  notificarCesion,
  saldarCesion,
} from "@/components/treasury/api";

export default function DetalleCesionPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [cesion, setCesion] = useState<DetalleCesion | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [clienteId, setClienteId] = useState("");
  const [medio, setMedio] = useState<MedioNotificacion>("EMAIL");
  const [fechaNotificacion, setFechaNotificacion] = useState(
    new Date().toISOString().slice(0, 10)
  );
  const [procesandoNotificar, setProcesandoNotificar] = useState(false);
  const [fechaSaldado, setFechaSaldado] = useState(
    new Date().toISOString().slice(0, 10)
  );
  const [procesandoSaldar, setProcesandoSaldar] = useState(false);

  const cargar = useCallback(async () => {
    try {
      setCargando(true);
      setError(null);
      setCesion(await obtenerCesion(id));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error al cargar cesión");
    } finally {
      setCargando(false);
    }
  }, [id]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const onNotificar = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setProcesandoNotificar(true);
      setError(null);
      await notificarCesion(id, {
        cliente_id: clienteId.trim(),
        medio,
        fecha_notificacion: fechaNotificacion,
      });
      setClienteId("");
      await cargar();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error al notificar cesión");
    } finally {
      setProcesandoNotificar(false);
    }
  };

  const onSaldar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!confirm("¿Saldar esta cesión?")) {
      return;
    }
    try {
      setProcesandoSaldar(true);
      setError(null);
      await saldarCesion(id, { fecha_saldado: fechaSaldado });
      await cargar();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error al saldar cesión");
    } finally {
      setProcesandoSaldar(false);
    }
  };

  if (cargando) {
    return <div className="p-8 text-center text-gray-500">Cargando cesión...</div>;
  }

  if (!cesion) {
    return (
      <div className="space-y-4">
        <div className="text-red-600">{error || "Cesión no encontrada"}</div>
        <button onClick={() => router.push("/cesiones")} className="text-blue-600 underline">
          Volver al listado
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs text-gray-500">
            <Link href="/cesiones" className="hover:underline">
              Cesiones
            </Link>{" "}
            / {cesion.entidad_financiera}
          </div>
          <h1 className="text-2xl font-bold">{cesion.entidad_financiera}</h1>
        </div>
        <span
          className={`rounded px-3 py-1 text-sm font-semibold ${
            cesion.estado === "saldada"
              ? "bg-green-100 text-green-800"
              : cesion.estado === "cancelada"
              ? "bg-red-100 text-red-800"
              : "bg-blue-100 text-blue-800"
          }`}
        >
          {cesion.estado.toUpperCase()}
        </span>
      </div>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 p-4 text-red-700">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <div className="space-y-4 rounded border bg-white p-6">
          <h2 className="text-lg font-semibold">Datos de la Cesión</h2>
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <dt className="text-gray-500">Total cedido:</dt>
            <dd className="font-mono font-bold text-blue-600">
              {cesion.importe_total_cedido}
            </dd>
            <dt className="text-gray-500">Comisión:</dt>
            <dd className="font-mono">{cesion.comision}</dd>
            <dt className="text-gray-500">Neto recibido:</dt>
            <dd className="font-mono font-bold">{cesion.importe_neto_recibido}</dd>
            <dt className="text-gray-500">Tipo comisión:</dt>
            <dd>{cesion.tipo_comision}</dd>
            <dt className="text-gray-500">Fecha:</dt>
            <dd>{cesion.fecha_cesion}</dd>
            <dt className="text-gray-500">Asiento:</dt>
            <dd className="font-mono text-xs truncate">{cesion.asiento_id}</dd>
            {cesion.notas && (
              <>
                <dt className="text-gray-500">Notas:</dt>
                <dd className="col-span-2 whitespace-pre-wrap rounded bg-gray-50 p-2 text-xs">
                  {cesion.notas}
                </dd>
              </>
            )}
          </dl>
        </div>

        <div className="overflow-hidden rounded border bg-white">
          <h2 className="border-b px-6 py-4 text-lg font-semibold">
            Vencimientos ({cesion.vencimientos.length})
          </h2>
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
              <tr>
                <th className="px-4 py-2">Recibo</th>
                <th className="px-4 py-2">Tercero</th>
                <th className="px-4 py-2 text-right">Importe</th>
                <th className="px-4 py-2">Estado</th>
              </tr>
            </thead>
            <tbody>
              {cesion.vencimientos.map((v) => (
                <tr key={v.vencimiento_id} className="border-t">
                  <td className="px-4 py-2 font-mono">{v.recibo_num}</td>
                  <td className="px-4 py-2">{v.tercero_nombre || v.tercero_id.slice(0, 8)}</td>
                  <td className="px-4 py-2 text-right font-mono">{v.importe}</td>
                  <td className="px-4 py-2">{v.estado}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="overflow-hidden rounded border bg-white">
        <h2 className="border-b px-6 py-4 text-lg font-semibold">
          Notificaciones ({cesion.notificaciones.length})
        </h2>
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-2">Fecha</th>
              <th className="px-4 py-2">Medio</th>
              <th className="px-4 py-2">Cliente</th>
              <th className="px-4 py-2">Estado</th>
            </tr>
          </thead>
          <tbody>
            {cesion.notificaciones.map((n) => (
              <tr key={n.id} className="border-t">
                <td className="px-4 py-2">{n.fecha_notificacion}</td>
                <td className="px-4 py-2">{n.medio}</td>
                <td className="px-4 py-2 font-mono text-xs">{n.cliente_id}</td>
                <td className="px-4 py-2">{n.estado}</td>
              </tr>
            ))}
            {cesion.notificaciones.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-gray-400">
                  Sin notificaciones aún.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {cesion.estado === "activa" && (
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          <form
            onSubmit={onNotificar}
            className="space-y-4 rounded border border-yellow-200 bg-yellow-50/50 p-6"
          >
            <h3 className="font-semibold text-yellow-900">Notificar al deudor</h3>
            <p className="text-xs text-yellow-700">
              Registra la notificación de la cesión al cliente titular de los
              vencimientos.
            </p>
            <div>
              <label className="block text-xs font-semibold text-gray-600">
                Cliente (UUID)
              </label>
              <input
                type="text"
                required
                className="mt-1 w-full rounded border bg-white p-2 text-sm font-mono"
                value={clienteId}
                onChange={(e) => setClienteId(e.target.value)}
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-gray-600">
                  Medio
                </label>
                <select
                  className="mt-1 w-full rounded border bg-white p-2 text-sm"
                  value={medio}
                  onChange={(e) => setMedio(e.target.value as MedioNotificacion)}
                >
                  <option value="EMAIL">EMAIL</option>
                  <option value="CORREO">CORREO</option>
                  <option value="REGISTRO">REGISTRO</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600">
                  Fecha notificación
                </label>
                <input
                  type="date"
                  required
                  className="mt-1 w-full rounded border bg-white p-2 text-sm"
                  value={fechaNotificacion}
                  onChange={(e) => setFechaNotificacion(e.target.value)}
                />
              </div>
            </div>
            <button
              type="submit"
              disabled={procesandoNotificar}
              className="w-full rounded bg-yellow-600 py-2 text-sm font-semibold text-white hover:bg-yellow-700 disabled:opacity-50"
            >
              {procesandoNotificar ? "Notificando..." : "Registrar Notificación"}
            </button>
          </form>

          <form
            onSubmit={onSaldar}
            className="space-y-4 rounded border border-green-200 bg-green-50/50 p-6"
          >
            <h3 className="font-semibold text-green-900">Saldar cesión</h3>
            <p className="text-xs text-green-700">
              Cierra la cesión cuando la entidad ha abonado los importes.
            </p>
            <div>
              <label className="block text-xs font-semibold text-gray-600">
                Fecha de saldado
              </label>
              <input
                type="date"
                required
                className="mt-1 w-full rounded border bg-white p-2 text-sm"
                value={fechaSaldado}
                onChange={(e) => setFechaSaldado(e.target.value)}
              />
            </div>
            <button
              type="submit"
              disabled={procesandoSaldar}
              className="w-full rounded bg-green-600 py-2 text-sm font-semibold text-white hover:bg-green-700 disabled:opacity-50"
            >
              {procesandoSaldar ? "Saldando..." : "Confirmar Saldado"}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}