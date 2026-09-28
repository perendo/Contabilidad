"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { ApiError, crearCalculo } from "@/components/fiscal/api";

export default function NuevoCalculoPage() {
  const router = useRouter();
  const [ejercicio, setEjercicio] = useState(new Date().getFullYear());
  const [provisional, setProvisional] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function guardar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    setGuardando(true);
    setError(null);
    try {
      const resultado = await crearCalculo({ ejercicio, provisional });
      router.push(`/fiscal/impuesto-sociedades/${resultado.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error al crear el cálculo");
    } finally {
      setGuardando(false);
    }
  }

  return (
    <main className="mx-auto max-w-2xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold">Nuevo cálculo de IS</h1>
        <p className="text-sm text-gray-500">
          El resultado contable, los pagos a cuenta y el tipo impositivo se obtienen del
          ejercicio y de la configuración fiscal.
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
            required
            value={ejercicio}
            onChange={(evento) => setEjercicio(evento.currentTarget.valueAsNumber)}
            className="mt-1 block w-full rounded border p-2 text-sm"
          />
        </label>

        <fieldset className="space-y-2">
          <legend className="text-sm font-semibold">Modalidad</legend>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name="provisional"
              checked={provisional}
              onChange={() => setProvisional(true)}
            />
            Provisional, permitido para cierres intermedios
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name="provisional"
              checked={!provisional}
              onChange={() => setProvisional(false)}
            />
            Definitivo, requiere el ejercicio cerrado
          </label>
        </fieldset>

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
            disabled={guardando}
            className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {guardando ? "Creando…" : "Crear cálculo"}
          </button>
        </div>
      </form>
    </main>
  );
}
