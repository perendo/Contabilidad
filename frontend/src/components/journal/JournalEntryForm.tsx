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
          placeholder="Cuenta Debe/Haber…"
        />
      </div>
      <label className="flex flex-col gap-1">
        Debe
        <input
          inputMode="decimal"
          value={linea.debe}
          onChange={(e) => onCambiar(indice, { debe: e.target.value })}
          className="border rounded px-2 py-1 w-28 font-mono"
        />
      </label>
      <label className="flex flex-col gap-1">
        Haber
        <input
          inputMode="decimal"
          value={linea.haber}
          onChange={(e) => onCambiar(indice, { haber: e.target.value })}
          className="border rounded px-2 py-1 w-28 font-mono"
        />
      </label>
      <button
        type="button"
        onClick={() => onQuitar(indice)}
        className="rounded px-2 py-1 border"
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
    if (!query.trim()) {
      setSugerencias([]);
      return;
    }
    try {
      const params = new URLSearchParams({ q: query, limit: "20" });
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
      cuadra: lineas.length >= 2 && debe > 0 && debe === haber,
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
      <div className="flex gap-3 items-center">
        <button
          type="button"
          onClick={() =>
            setLineas((prev) => [
              ...prev,
              { cuentaId: "", cuentaCodigo: "", debe: "", haber: "" },
            ])
          }
          className="rounded px-3 py-1 border"
        >
          Añadir línea (Tab)
        </button>
        <span className={cuadra ? "text-emerald-700" : "text-amber-700"}>
          Debe {totalDebe.toFixed(4)} · Haber {totalHaber.toFixed(4)} ·{" "}
          {cuadra ? "Cuadra (informativo)" : "No cuadra"}
        </span>
        <button
          type="button"
          disabled={!cuadra}
          onClick={() => onGuardar(lineas)}
          className="bg-blue-600 text-white rounded px-3 py-1 disabled:opacity-50"
        >
          Guardar
        </button>
      </div>
    </div>
  );
}
