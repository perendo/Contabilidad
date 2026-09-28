"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  cobrarEfecto,
  DetalleEfecto,
  impagarEfecto,
  obtenerEfecto,
} from "@/components/treasury/api";

export default function DetalleEfectoPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [efecto, setEfecto] = useState<DetalleEfecto | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Formulario cobro
  const [fechaCobro, setFechaCobro] = useState(
    new Date().toISOString().slice(0, 10)
  );
  const [cuentaBancoCobro, setCuentaBancoCobro] = useState("572");
  const [procesandoCobro, setProcesandoCobro] = useState(false);

  // Formulario impago
  const [fechaImpago, setFechaImpago] = useState(
    new Date().toISOString().slice(0, 10)
  );
  const [motivoImpago, setMotivoImpago] = useState("");
  const [gastosImpago, setGastosImpago] = useState("0");
  const [cuentaBancoImpago] = useState("572");
  const [procesandoImpago, setProcesandoImpago] = useState(false);

  const cargar = useCallback(async () => {
    try {
      setCargando(true);
      setError(null);
      const res = await obtenerEfecto(id);
      setEfecto(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error al cargar efecto");
    } finally {
      setCargando(false);
    }
  }, [id]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const onCobrar = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setProcesandoCobro(true);
      setError(null);
      await cobrarEfecto(id, {
        fecha_cobro: fechaCobro,
        cuenta_banco: cuentaBancoCobro,
      });
      await cargar();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error al cobrar efecto");
    } finally {
      setProcesandoCobro(false);
    }
  };

  const onImpagar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!confirm("¿Registrar el impago de este efecto? Se creará un asiento REVERSAL.")) {
      return;
    }
    try {
      setProcesandoImpago(true);
      setError(null);
      await impagarEfecto(id, {
        fecha_impago: fechaImpago,
        motivo: motivoImpago.trim() || undefined,
        gastos_devolucion: gastosImpago.trim() || "0",
        cuenta_banco: cuentaBancoImpago,
      });
      await cargar();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error al registrar impago");
    } finally {
      setProcesandoImpago(false);
    }
  };

  if (cargando) {
    return <div className="p-8 text-center text-gray-500">Cargando efecto...</div>;
  }

  if (!efecto) {
    return (
      <div className="space-y-4">
        <div className="text-red-600">{error || "Efecto no encontrado"}</div>
        <button
          onClick={() => router.push("/efectos")}
          className="text-blue-600 underline"
        >
          Volver a la cartera
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs text-gray-500">
            <Link href="/efectos" className="hover:underline">
              Cartera
            </Link>{" "}
            / {efecto.tipo_efecto}
          </div>
          <h1 className="text-2xl font-bold font-mono">
            {efecto.numero_documento}
          </h1>
        </div>
        <span
          className={`rounded px-3 py-1 text-sm font-semibold ${
            efecto.estado === "cobrado"
              ? "bg-green-100 text-green-800"
              : efecto.estado === "impagado"
              ? "bg-red-100 text-red-800"
              : "bg-yellow-100 text-yellow-800"
          }`}
        >
          {efecto.estado.toUpperCase()}
        </span>
      </div>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 p-4 text-red-700">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <div className="space-y-4 rounded border bg-white p-6">
          <h2 className="text-lg font-semibold">Datos del Efecto</h2>
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <dt className="text-gray-500">Tipo:</dt>
            <dd className="font-semibold">{efecto.tipo_efecto}</dd>
            <dt className="text-gray-500">Importe:</dt>
            <dd className="font-mono font-bold text-blue-600">
              {efecto.importe} {efecto.moneda}
            </dd>
            <dt className="text-gray-500">Tercero:</dt>
            <dd className="font-mono text-xs">
              {efecto.tercero_nombre || efecto.tercero_id}
            </dd>
            <dt className="text-gray-500">Emisión:</dt>
            <dd>{efecto.fecha_emision}</dd>
            <dt className="text-gray-500">Vencimiento:</dt>
            <dd>{efecto.fecha_vencimiento}</dd>
            {efecto.notas && (
              <>
                <dt className="text-gray-500">Notas:</dt>
                <dd className="col-span-2 whitespace-pre-wrap rounded bg-gray-50 p-2 text-xs">
                  {efecto.notas}
                </dd>
              </>
            )}
          </dl>
        </div>

        <div className="space-y-4 rounded border bg-white p-6">
          <h2 className="text-lg font-semibold">Asientos Contables</h2>
          {efecto.asientos.asiento_cobro_id ? (
            <div className="rounded bg-green-50 p-3 text-sm">
              <div className="font-semibold text-green-800">
                Asiento de Cobro (COBRO)
              </div>
              <div className="text-xs text-green-700">
                UUID: {efecto.asientos.asiento_cobro_id.id}
              </div>
              <div className="text-xs text-green-700">
                Concepto: {efecto.asientos.asiento_cobro_id.concepto}
              </div>
            </div>
          ) : null}
          {efecto.asientos.asiento_impago_id ? (
            <div className="rounded bg-red-50 p-3 text-sm">
              <div className="font-semibold text-red-800">
                Asiento de Impago (REVERSAL)
              </div>
              <div className="text-xs text-red-700">
                UUID: {efecto.asientos.asiento_impago_id.id}
              </div>
              <div className="text-xs text-red-700">
                Concepto: {efecto.asientos.asiento_impago_id.concepto}
              </div>
            </div>
          ) : null}
          {!efecto.asientos.asiento_cobro_id &&
            !efecto.asientos.asiento_impago_id && (
              <div className="text-sm text-gray-400">
                No hay asientos registrados aún para este efecto.
              </div>
            )}
        </div>
      </div>

      {efecto.estado === "emitido" && (
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          {/* Cobrar */}
          <form
            onSubmit={onCobrar}
            className="space-y-4 rounded border border-green-200 bg-green-50/50 p-6"
          >
            <h3 className="font-semibold text-green-900">Cobrar Efecto</h3>
            <p className="text-xs text-green-700">
              Genera asiento Debe 572 | Haber 431 por el importe total.
            </p>
            <div>
              <label className="block text-xs font-semibold text-gray-600">
                Fecha de cobro
              </label>
              <input
                type="date"
                required
                className="mt-1 w-full rounded border bg-white p-2 text-sm"
                value={fechaCobro}
                onChange={(e) => setFechaCobro(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600">
                Cuenta Banco (572)
              </label>
              <input
                type="text"
                required
                className="mt-1 w-full rounded border bg-white p-2 text-sm font-mono"
                value={cuentaBancoCobro}
                onChange={(e) => setCuentaBancoCobro(e.target.value)}
              />
            </div>
            <button
              type="submit"
              disabled={procesandoCobro}
              className="w-full rounded bg-green-600 py-2 text-sm font-semibold text-white hover:bg-green-700 disabled:opacity-50"
            >
              {procesandoCobro ? "Cobrando..." : "Confirmar Cobro"}
            </button>
          </form>

          {/* Impagar */}
          <form
            onSubmit={onImpagar}
            className="space-y-4 rounded border border-red-200 bg-red-50/50 p-6"
          >
            <h3 className="font-semibold text-red-900">Registrar Impago</h3>
            <p className="text-xs text-red-700">
              Genera asiento REVERSAL (Debe 431 + 626 gastos | Haber 572) y
              reabre los vencimientos del tercero a estado pendiente.
            </p>
            <div>
              <label className="block text-xs font-semibold text-gray-600">
                Fecha de impago
              </label>
              <input
                type="date"
                required
                className="mt-1 w-full rounded border bg-white p-2 text-sm"
                value={fechaImpago}
                onChange={(e) => setFechaImpago(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600">
                Gastos de devolución (€)
              </label>
              <input
                type="text"
                className="mt-1 w-full rounded border bg-white p-2 text-sm font-mono"
                placeholder="0.0000"
                value={gastosImpago}
                onChange={(e) => setGastosImpago(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600">
                Motivo del impago
              </label>
              <input
                type="text"
                className="mt-1 w-full rounded border bg-white p-2 text-sm"
                placeholder="Fondos insuficientes..."
                value={motivoImpago}
                onChange={(e) => setMotivoImpago(e.target.value)}
              />
            </div>
            <button
              type="submit"
              disabled={procesandoImpago}
              className="w-full rounded bg-red-600 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
            >
              {procesandoImpago ? "Registrando..." : "Confirmar Impago"}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
