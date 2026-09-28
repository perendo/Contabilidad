"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import JournalEntryForm, {
  type LineaAsiento,
} from "../../../components/journal/JournalEntryForm";
import { ApiError } from "../../../components/treasury/api";
import { post } from "../../../services/client";

export default function NuevoAsientoPage() {
  const router = useRouter();
  const [fecha, setFecha] = useState("2026-05-01");
  const [concepto, setConcepto] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  async function guardar(lineas: LineaAsiento[]) {
    setError(null);
    setGuardando(true);
    try {
      const creado = await post<{ id: string }>("/api/v1/journal/entries", {
        fecha,
        concepto,
        lineas: lineas.map((l) => ({
          account_id: Number(l.cuentaId),
          debit: l.debe || "0",
          credit: l.haber || "0",
        })),
      });
      router.push(`/asientos/${creado.id}`);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    } finally {
      setGuardando(false);
    }
  }

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Nuevo asiento</h1>
      <div className="flex gap-3 mb-4">
        <label className="flex flex-col gap-1">
          Fecha
          <input type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} className="border rounded px-3 py-1" />
        </label>
        <label className="flex flex-col gap-1 flex-1">
          Concepto
          <input value={concepto} onChange={(e) => setConcepto(e.target.value)} className="border rounded px-3 py-1" />
        </label>
      </div>
      {error && <p className="text-red-600 mb-4">{error}</p>}
      {guardando && <p className="mb-4">Guardando…</p>}
      <JournalEntryForm onGuardar={guardar} />
    </main>
  );
}
