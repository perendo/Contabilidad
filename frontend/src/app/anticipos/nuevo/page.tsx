"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { crearAnticipo, TipoAnticipo } from "@/components/treasury/api";

export default function NuevoAnticipoPage() {
  const router = useRouter();
  const [terceroId, setTerceroId] = useState("");
  const [tipo, setTipo] = useState<TipoAnticipo>("CLIENTE");
  const [fecha, setFecha] = useState(new Date().toISOString().slice(0, 10));
  const [importe, setImporte] = useState("");
  const [concepto, setConcepto] = useState("");
  const [cuenta, setCuenta] = useState("");
  const [notas, setNotas] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const guardar = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setGuardando(true);
      setError(null);
      const res = await crearAnticipo({
        tercero_id: terceroId.trim(),
        tipo,
        fecha,
        importe: importe.trim(),
        concepto: concepto.trim(),
        cuenta_contable: cuenta.trim() || undefined,
        notas: notas.trim() || undefined,
      });
      router.push(`/anticipos/${res.id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error al registrar anticipo");
    } finally {
      setGuardando(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Nuevo Anticipo</h1>
        <p className="text-sm text-gray-500">
          Anticipo de cliente (572 ↔ 438) o de proveedor (407/408 ↔ 572)
        </p>
      </div>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 p-4 text-red-700">
          {error}
        </div>
      )}

      <form onSubmit={guardar} className="space-y-4 rounded border bg-white p-6">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-semibold">Tipo</label>
            <select
              className="mt-1 w-full rounded border p-2 text-sm"
              value={tipo}
              onChange={(e) => {
                setTipo(e.target.value as TipoAnticipo);
                setCuenta("");
              }}
            >
              <option value="CLIENTE">Cliente (cuenta 438)</option>
              <option value="PROVEEDOR">Proveedor (cuenta 407/408)</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-semibold">Fecha</label>
            <input
              type="date"
              required
              className="mt-1 w-full rounded border p-2 text-sm"
              value={fecha}
              onChange={(e) => setFecha(e.target.value)}
            />
          </div>
        </div>

        <div>
          <label className="block text-sm font-semibold">Tercero (UUID)</label>
          <input
            type="text"
            required
            className="mt-1 w-full rounded border p-2 text-sm font-mono"
            placeholder="UUID del cliente o proveedor"
            value={terceroId}
            onChange={(e) => setTerceroId(e.target.value)}
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
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
            <label className="block text-sm font-semibold">
              Cuenta contable (opcional)
            </label>
            <input
              type="text"
              pattern="^(407|408|438)$"
              className="mt-1 w-full rounded border p-2 text-sm font-mono"
              placeholder={tipo === "PROVEEDOR" ? "407 o 408" : "438"}
              value={cuenta}
              onChange={(e) => setCuenta(e.target.value)}
            />
          </div>
        </div>

        <div>
          <label className="block text-sm font-semibold">Concepto</label>
          <input
            type="text"
            required
            maxLength={255}
            className="mt-1 w-full rounded border p-2 text-sm"
            placeholder="Anticipo curso formación"
            value={concepto}
            onChange={(e) => setConcepto(e.target.value)}
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
            {guardando ? "Registrando..." : "Registrar Anticipo"}
          </button>
        </div>
      </form>
    </div>
  );
}