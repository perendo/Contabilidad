"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  MedioCobro,
  registrarCobroMedio,
} from "@/components/treasury/api";

export default function NuevoCobroMedioPage() {
  const router = useRouter();
  const [vencimientoId, setVencimientoId] = useState("");
  const [medio, setMedio] = useState<MedioCobro>("TRANSFERENCIA");
  const [fechaCobro, setFechaCobro] = useState(
    new Date().toISOString().slice(0, 10)
  );
  const [cuentaBanco, setCuentaBanco] = useState("572");
  const [comision, setComision] = useState("0");
  const [tipoComision, setTipoComision] = useState("OTRA");
  const [bancoCodigo, setBancoCodigo] = useState("");
  const [porcentaje, setPorcentaje] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resultado, setResultado] = useState<{
    id: string;
    importe_total: string;
    importe_comision: string;
    importe_neto: string;
    asiento_cobro_id: string;
  } | null>(null);

  const guardar = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setGuardando(true);
      setError(null);
      const res = await registrarCobroMedio({
        vencimiento_id: vencimientoId.trim(),
        medio_cobro: medio,
        fecha_cobro: fechaCobro,
        cuenta_banco: cuentaBanco,
        importe_comision: comision.trim() || "0",
        tipo_comision: tipoComision,
        banco_codigo: bancoCodigo.trim() || undefined,
        porcentaje: porcentaje.trim() || undefined,
      });
      setResultado(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error al registrar cobro");
    } finally {
      setGuardando(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Cobro por Medio</h1>
        <p className="text-sm text-gray-500">
          Registrar cobro de un vencimiento por TPV, tarjeta o transferencia con comisión bancaria
        </p>
      </div>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 p-4 text-red-700">
          {error}
        </div>
      )}

      {resultado && (
        <div className="space-y-2 rounded border border-green-200 bg-green-50 p-4 text-green-900">
          <div className="font-semibold">¡Cobro registrado con éxito!</div>
          <div className="text-sm">
            Total: <b>{resultado.importe_total} €</b> | Comisión:{" "}
            <b>{resultado.importe_comision} €</b> | Neto al banco:{" "}
            <b>{resultado.importe_neto} €</b>
          </div>
          <div className="text-xs text-green-700 font-mono">
            Asiento contable: {resultado.asiento_cobro_id}
          </div>
          <div className="pt-2">
            <button
              onClick={() => router.push("/tesoreria")}
              className="rounded bg-green-700 px-3 py-1 text-xs text-white hover:bg-green-800"
            >
              Ir al panel de tesorería
            </button>
          </div>
        </div>
      )}

      <form onSubmit={guardar} className="space-y-4 rounded border bg-white p-6">
        <div>
          <label className="block text-sm font-semibold">Vencimiento (UUID)</label>
          <input
            type="text"
            required
            className="mt-1 w-full rounded border p-2 text-sm font-mono"
            placeholder="UUID del vencimiento pendiente"
            value={vencimientoId}
            onChange={(e) => setVencimientoId(e.target.value)}
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-semibold">Medio de Cobro</label>
            <select
              className="mt-1 w-full rounded border p-2 text-sm"
              value={medio}
              onChange={(e) => setMedio(e.target.value as MedioCobro)}
            >
              <option value="TRANSFERENCIA">Transferencia</option>
              <option value="TARJETA">Tarjeta / TPV</option>
              <option value="CHEQUE">Cheque</option>
              <option value="PAGARE">Pagaré</option>
              <option value="LETRA">Letra</option>
              <option value="CAJA">Caja efectivo</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-semibold">Fecha de Cobro</label>
            <input
              type="date"
              required
              className="mt-1 w-full rounded border p-2 text-sm"
              value={fechaCobro}
              onChange={(e) => setFechaCobro(e.target.value)}
            />
          </div>
        </div>

        <div>
          <label className="block text-sm font-semibold">Cuenta Banco / Caja</label>
          <input
            type="text"
            required
            className="mt-1 w-full rounded border p-2 text-sm font-mono"
            value={cuentaBanco}
            onChange={(e) => setCuentaBanco(e.target.value)}
          />
        </div>

        <div className="rounded border bg-gray-50 p-4 space-y-3">
          <div className="text-sm font-semibold text-gray-700">Comisión Bancaria (cuenta 626)</div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs text-gray-500">Importe (€)</label>
              <input
                type="text"
                className="mt-1 w-full rounded border p-2 text-sm font-mono"
                placeholder="0.0000"
                value={comision}
                onChange={(e) => setComision(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500">Tipo Comisión</label>
              <select
                className="mt-1 w-full rounded border p-2 text-sm"
                value={tipoComision}
                onChange={(e) => setTipoComision(e.target.value)}
              >
                <option value="TPV">TPV</option>
                <option value="TRANSFERENCIA">Transferencia</option>
                <option value="CHEQUE">Cheque</option>
                <option value="CAJA">Caja</option>
                <option value="OTRA">Otra</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-500">% Aplicado (opcional)</label>
              <input
                type="text"
                className="mt-1 w-full rounded border p-2 text-sm font-mono"
                placeholder="1.50"
                value={porcentaje}
                onChange={(e) => setPorcentaje(e.target.value)}
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-gray-500">Código Banco (opcional)</label>
            <input
              type="text"
              className="mt-1 w-full rounded border p-2 text-sm font-mono"
              placeholder="0049"
              value={bancoCodigo}
              onChange={(e) => setBancoCodigo(e.target.value)}
            />
          </div>
        </div>

        <div className="flex justify-end space-x-3 pt-4">
          <button
            type="button"
            onClick={() => router.back()}
            className="rounded border px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={guardando}
            className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {guardando ? "Registrando..." : "Registrar Cobro"}
          </button>
        </div>
      </form>
    </div>
  );
}
