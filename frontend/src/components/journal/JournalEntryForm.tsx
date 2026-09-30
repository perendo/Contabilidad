"use client";

import { useMemo, useState } from "react";
import {
  AccountAutocomplete,
  type CuentaSugerida,
} from "../acct/AccountAutocomplete";
import { ApiError } from "../treasury/api";
import { get } from "../../services/client";

export interface LineaAsiento {
  cuentaId: string;
  cuentaCodigo: string;
  debe: string;
  haber: string;
}

interface Sugerencias {
  items: CuentaSugerida[];
}

function LineaRow({
  linea,
  indice,
  sugerencias,
  onBuscar,
  onCambiar,
  onQuitar,
}: {
  linea: LineaAsiento;
  indice: number;
  sugerencias: CuentaSugerida[];
  onBuscar: (query: string) => void;
  onCambiar: (indice: number, parche: Partial<LineaAsiento>) => void;
  onQuitar: (indice: number) => void;
}) {
  return (
    <div className="flex gap-2 items-end">
      <div className="flex-1">
        <AccountAutocomplete
          value={linea.cuentaId}
          onChange={(cuenta) =>
            onCambiar(indice, {
              cuentaId: cuenta ? String(cuenta.id) : "",
              cuentaCodigo: cuenta ? cuenta.code : "",
            })
          }
          onSearch={onBuscar}
          sugerencias={sugerencias}
          placeholder="Escribe código/nombre o doble clic para ver PGC…"
        />
      </div>

      <label className="flex flex-col gap-1">
        Debe
        <input
          inputMode="decimal"
          value={linea.debe}
          onChange={(e) => onCambiar(indice, { debe: e.target.value })}
          className="border rounded px-2 py-1 w-28 font-mono bg-white text-slate-900 border-slate-300"
          placeholder="0,00"
        />
      </label>

      <label className="flex flex-col gap-1">
        Haber
        <input
          inputMode="decimal"
          value={linea.haber}
          onChange={(e) => onCambiar(indice, { haber: e.target.value })}
          className="border rounded px-2 py-1 w-28 font-mono bg-white text-slate-900 border-slate-300"
          placeholder="0,00"
        />
      </label>

      <button
        type="button"
        onClick={() => onQuitar(indice)}
        className="rounded px-2.5 py-1.5 border border-slate-300 hover:bg-slate-100 text-slate-600 hover:text-red-600 transition-colors"
        aria-label={`Quitar línea ${indice + 1}`}
      >
        ✕
      </button>
    </div>
  );
}

export default function JournalEntryForm({
  onGuardar,
}: {
  onGuardar: (lineas: LineaAsiento[]) => void;
}) {
  const [lineas, setLineas] = useState<LineaAsiento[]>([
    { cuentaId: "", cuentaCodigo: "", debe: "", haber: "" },
    { cuentaId: "", cuentaCodigo: "", debe: "", haber: "" },
  ]);
  const [sugerencias, setSugerencias] = useState<CuentaSugerida[]>([]);

  async function buscar(query: string) {
    const qLimpia = query.trim();
    // Si viene vacía (ej. al hacer doble clic), buscar por defecto "4" o "5" para listar cuentas habituales
    const termino = qLimpia.length >= 1 ? qLimpia : "4";
    try {
      const params = new URLSearchParams({ q: termino, limit: "50" });
      const cuerpo = await get<Sugerencias>(`/api/v1/accounts/suggest?${params}`);
      setSugerencias(cuerpo.items);
    } catch (e) {
      if (!(e instanceof ApiError)) throw e;
      setSugerencias([]);
    }
  }

  function cambiar(indice: number, parche: Partial<LineaAsiento>) {
    setLineas((prev) => prev.map((l, i) => (i === indice ? { ...l, ...parche } : l)));
  }

  const { totalDebe, totalHaber, cuadra } = useMemo(() => {
    const debe = lineas.reduce((s, l) => s + (Number(l.debe) || 0), 0);
    const haber = lineas.reduce((s, l) => s + (Number(l.haber) || 0), 0);
    return {
      totalDebe: debe,
      totalHaber: haber,
      cuadra: lineas.length >= 2 && debe > 0 && Math.abs(debe - haber) < 0.001,
    };
  }, [lineas]);

  return (
    <div className="flex flex-col gap-3">
      {lineas.map((linea, i) => (
        <LineaRow
          key={i}
          linea={linea}
          indice={i}
          sugerencias={sugerencias}
          onBuscar={buscar}
          onCambiar={cambiar}
          onQuitar={(idx) => setLineas((prev) => prev.filter((_, j) => j !== idx))}
        />
      ))}

      <div className="flex flex-wrap gap-3 items-center justify-between pt-2">
        <button
          type="button"
          onClick={() =>
            setLineas((prev) => [
              ...prev,
              { cuentaId: "", cuentaCodigo: "", debe: "", haber: "" },
            ])
          }
          className="rounded-lg px-3 py-1.5 border border-slate-300 bg-white hover:bg-slate-50 text-slate-800 text-xs font-semibold shadow-sm transition-colors"
        >
          + Añadir línea
        </button>

        <div className="flex items-center gap-4 text-xs font-mono">
          <span>
            Debe: <strong className="text-emerald-700">{totalDebe.toFixed(2)} €</strong>
          </span>
          <span>
            Haber: <strong className="text-emerald-700">{totalHaber.toFixed(2)} €</strong>
          </span>
          <span
            className={`px-2 py-0.5 rounded text-[11px] font-sans font-bold ${
              cuadra
                ? "bg-emerald-100 text-emerald-800 border border-emerald-300"
                : "bg-amber-100 text-amber-800 border border-amber-300"
            }`}
          >
            {cuadra ? "Asiento Cuadrado" : "Descuadrado"}
          </span>
        </div>
      </div>

      <div className="pt-4 border-t border-slate-200">
        <button
          type="button"
          disabled={!cuadra}
          onClick={() => onGuardar(lineas)}
          className="w-full sm:w-auto px-6 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-bold text-sm shadow-sm disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          Guardar Asiento Contable
        </button>
      </div>
    </div>
  );
}
