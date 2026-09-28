"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  crearCesion,
  TipoComisionCesion,
  VencimientoItem,
  listarVencimientos,
} from "@/components/treasury/api";

export default function NuevaCesionPage() {
  const router = useRouter();
  const [entidad, setEntidad] = useState("");
  const [fechaCesion, setFechaCesion] = useState(
    new Date().toISOString().slice(0, 10)
  );
  const [comision, setComision] = useState("0.0000");
  const [tipoComision, setTipoComision] = useState<TipoComisionCesion>(
    "IMPORTE_FIJO"
  );
  const [vencimientos, setVencimientos] = useState<VencimientoItem[]>([]);
  const [seleccionados, setSeleccionados] = useState<string[]>([]);
  const [notas, setNotas] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listarVencimientos({ estado: "pendiente", limit: 200 })
      .then((res) => setVencimientos(res.items))
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Error al cargar vencimientos")
      );
  }, []);

  const toggle = (id: string) => {
    setSeleccionados((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const totalSelecionado = vencimientos
    .filter((v) => seleccionados.includes(v.id))
    .reduce((acc, v) => acc + Number(v.importe), 0);

  const guardar = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setGuardando(true);
      setError(null);
      const res = await crearCesion({
        entidad_financiera: entidad.trim(),
        fecha_cesion: fechaCesion,
        vencimiento_ids: seleccionados,
        comision: comision.trim(),
        tipo_comision: tipoComision,
        notas: notas.trim() || undefined,
      });
      router.push(`/cesiones/${res.id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error al crear cesión");
    } finally {
      setGuardando(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Nueva Cesión de Cobros</h1>
        <p className="text-sm text-gray-500">
          Cede vencimientos pendientes a una entidad; asiento Debe 572 (neto) +
          662 (comisión) | Haber 430 (total)
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
            <label className="block text-sm font-semibold">
              Entidad financiera
            </label>
            <input
              type="text"
              required
              maxLength={100}
              className="mt-1 w-full rounded border p-2 text-sm"
              placeholder="Banco Factor S.A."
              value={entidad}
              onChange={(e) => setEntidad(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm font-semibold">Fecha de cesión</label>
            <input
              type="date"
              required
              className="mt-1 w-full rounded border p-2 text-sm"
              value={fechaCesion}
              onChange={(e) => setFechaCesion(e.target.value)}
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-semibold">Tipo de comisión</label>
            <select
              className="mt-1 w-full rounded border p-2 text-sm"
              value={tipoComision}
              onChange={(e) => setTipoComision(e.target.value as TipoComisionCesion)}
            >
              <option value="IMPORTE_FIJO">Importe fijo</option>
              <option value="PORCENTAJE">Porcentaje</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-semibold">
              Comisión (
              {tipoComision === "PORCENTAJE" ? "%" : "€"})
            </label>
            <input
              type="text"
              required
              pattern="^\d+(\.\d{1,4})?$"
              className="mt-1 w-full rounded border p-2 text-sm font-mono"
              value={comision}
              onChange={(e) => setComision(e.target.value)}
            />
          </div>
        </div>

        <div>
          <label className="block text-sm font-semibold">
            Vencimientos pendientes (seleccionados: {seleccionados.length}, total{" "}
            {totalSelecionado.toFixed(4)} €)
          </label>
          <div className="mt-2 max-h-64 overflow-y-auto rounded border">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-gray-50 text-left text-xs uppercase text-gray-500">
                <tr>
                  <th className="px-3 py-2"></th>
                  <th className="px-3 py-2">Recibo</th>
                  <th className="px-3 py-2">Fecha</th>
                  <th className="px-3 py-2 text-right">Importe</th>
                </tr>
              </thead>
              <tbody>
                {vencimientos.map((v) => (
                  <tr key={v.id} className="border-t">
                    <td className="px-3 py-2">
                      <input
                        type="checkbox"
                        checked={seleccionados.includes(v.id)}
                        onChange={() => toggle(v.id)}
                      />
                    </td>
                    <td className="px-3 py-2 font-mono">{v.recibo_num}</td>
                    <td className="px-3 py-2">{v.fecha_vencimiento}</td>
                    <td className="px-3 py-2 text-right font-mono">
                      {v.saldo_pendiente}
                    </td>
                  </tr>
                ))}
                {vencimientos.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-3 py-8 text-center text-gray-400">
                      No hay vencimientos pendientes.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <label className="block text-sm font-semibold">Notas (opcional)</label>
          <textarea
            className="mt-1 w-full rounded border p-2 text-sm"
            rows={2}
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
            disabled={guardando || seleccionados.length === 0}
            className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {guardando
              ? "Creando..."
              : `Crear Cesión (${seleccionados.length} vencimientos)`}
          </button>
        </div>
      </form>
    </div>
  );
}