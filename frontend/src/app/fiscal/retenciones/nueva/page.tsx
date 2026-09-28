"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { ApiError, crearLiquidacion } from "@/components/fiscal/api";

const TRIMESTRES = [1, 2, 3, 4];

export default function NuevaLiquidacionPage() {
  const router = useRouter();
  const [ejercicio, setEjercicio] = useState(new Date().getFullYear());
  const [trimestre, setTrimestre] = useState(1);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function guardar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    setGuardando(true);
    setError(null);
    try {
      const liquidacion = await crearLiquidacion({ ejercicio, trimestre });
      router.push(`/fiscal/retenciones/${liquidacion.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error al crear la liquidación");
    } finally {
      setGuardando(false);
    }
  }

  return (
    <main className="mx-auto max-w-2xl space-y-6 p-6">
      <div>
        <div className="text-xs text-gray-500">
          <Link href="/fiscal/retenciones" className="hover:underline">
            Retenciones IRPF
          </Link>{" "}
          / Nueva liquidación
        </div>
        <h1 className="mt-1 text-2xl font-bold">Nueva liquidación trimestral</h1>
        <p className="text-sm text-gray-500">
          Se acumularán las retenciones IRPF de las operaciones del trimestre natural indicado.
        </p>
      </div>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 p-4 text-red-700">
          {error}
        </div>
      )}

      <form onSubmit={guardar} className="space-y-5 rounded border bg-white p-6">
        <label className="block text-sm font-semibold" htmlFor="ejercicio">
          Ejercicio
          <input
            id="ejercicio"
            type="number"
            min="1900"
            max="9999"
            required
            value={ejercicio}
            onChange={(evento) => setEjercicio(evento.currentTarget.valueAsNumber)}
            className="mt-1 block w-full rounded border p-2 text-sm"
          />
        </label>

        <label className="block text-sm font-semibold" htmlFor="trimestre">
          Trimestre
          <select
            id="trimestre"
            value={trimestre}
            onChange={(evento) => setTrimestre(Number(evento.target.value))}
            className="mt-1 block w-full rounded border p-2 text-sm"
          >
            {TRIMESTRES.map((valor) => (
              <option key={valor} value={valor}>
                Q{valor} ({["enero-marzo", "abril-junio", "julio-septiembre", "octubre-diciembre"][valor - 1]})
              </option>
            ))}
          </select>
        </label>

        <div className="rounded border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
          La liquidación se asociará a la empresa activa de la sesión. No se puede crear dos veces
          el mismo trimestre.
        </div>

        <div className="flex justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={() => router.back()}
            className="rounded border px-4 py-2 text-sm hover:bg-gray-50"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={guardando || !Number.isInteger(ejercicio) || !Number.isInteger(trimestre)}
            className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {guardando ? "Creando…" : "Crear liquidación"}
          </button>
        </div>
      </form>
    </main>
  );
}
