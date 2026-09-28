"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { crearEfecto, TipoEfecto } from "@/components/treasury/api";

export default function NuevoEfectoPage() {
  const router = useRouter();
  const [terceroId, setTerceroId] = useState("");
  const [tipo, setTipo] = useState<TipoEfecto>("CHEQUE");
  const [numero, setNumero] = useState("");
  const [fechaEmision, setFechaEmision] = useState(
    new Date().toISOString().slice(0, 10)
  );
  const [fechaVencimiento, setFechaVencimiento] = useState("");
  const [importe, setImporte] = useState("");
  const [notas, setNotas] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const guardar = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setGuardando(true);
      setError(null);
      const res = await crearEfecto({
        tercero_id: terceroId.trim(),
        tipo_efecto: tipo,
        numero_documento: numero.trim(),
        fecha_emision: fechaEmision,
        fecha_vencimiento: fechaVencimiento,
        importe: importe.trim(),
        notas: notas.trim() || undefined,
      });
      router.push(`/efectos/${res.id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error al registrar efecto");
    } finally {
      setGuardando(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Nuevo Efecto</h1>
        <p className="text-sm text-gray-500">
          Registrar cheque, pagaré o letra de cambio
        </p>
      </div>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 p-4 text-red-700">
          {error}
        </div>
      )}

      <form onSubmit={guardar} className="space-y-4 rounded border bg-white p-6">
        <div>
          <label className="block text-sm font-semibold">Tercero (UUID)</label>
          <input
            type="text"
            required
            className="mt-1 w-full rounded border p-2 text-sm font-mono"
            placeholder="UUID del cliente o deudor"
            value={terceroId}
            onChange={(e) => setTerceroId(e.target.value)}
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-semibold">Tipo de Efecto</label>
            <select
              className="mt-1 w-full rounded border p-2 text-sm"
              value={tipo}
              onChange={(e) => setTipo(e.target.value as TipoEfecto)}
            >
              <option value="CHEQUE">Cheque</option>
              <option value="PAGARE">Pagaré</option>
              <option value="LETRA">Letra de cambio</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-semibold">Nº Documento</label>
            <input
              type="text"
              required
              className="mt-1 w-full rounded border p-2 text-sm font-mono"
              placeholder="CHQ-001"
              value={numero}
              onChange={(e) => setNumero(e.target.value)}
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-semibold">Fecha Emisión</label>
            <input
              type="date"
              required
              className="mt-1 w-full rounded border p-2 text-sm"
              value={fechaEmision}
              onChange={(e) => setFechaEmision(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm font-semibold">Fecha Vencimiento</label>
            <input
              type="date"
              required
              className="mt-1 w-full rounded border p-2 text-sm"
              value={fechaVencimiento}
              onChange={(e) => setFechaVencimiento(e.target.value)}
            />
          </div>
        </div>

        <div>
          <label className="block text-sm font-semibold">Importe (€)</label>
          <input
            type="text"
            required
            pattern="^\d+(\.\d{1,4})?$"
            className="mt-1 w-full rounded border p-2 text-sm font-mono"
            placeholder="1000.0000"
            value={importe}
            onChange={(e) => setImporte(e.target.value)}
          />
        </div>

        <div>
          <label className="block text-sm font-semibold">Notas (opcional)</label>
          <textarea
            className="mt-1 w-full rounded border p-2 text-sm"
            rows={3}
            value={notas}
            onChange={(e) => setNotas(e.target.value)}
          />
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
            {guardando ? "Registrando..." : "Registrar Efecto"}
          </button>
        </div>
      </form>
    </div>
  );
}
