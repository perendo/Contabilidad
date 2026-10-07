"use client";

import { useMemo, useRef, useState } from "react";

import {
  AccountAutocomplete,
  type CuentaSugerida,
} from "../acct/AccountAutocomplete";
import CentroSelect from "../costcenters/CentroSelect";
import { ApiError } from "../treasury/api";
import { get } from "../../services/client";

export interface LineaMultilinea {
  cuentaId: string;
  cuentaCodigo: string;
  debe: string;
  haber: string;
  detalle: string;
  centroId: string;
}

interface Sugerencias {
  items: CuentaSugerida[];
}

function filaVacia(): LineaMultilinea {
  return { cuentaId: "", cuentaCodigo: "", debe: "", haber: "", detalle: "", centroId: "" };
}

export default function LineEditor({
  onGuardar,
  onGuardarBorrador,
  etiquetaGuardar = "Guardar asiento",
  guardando = false,
}: {
  onGuardar: (lineas: LineaMultilinea[]) => void;
  onGuardarBorrador?: (lineas: LineaMultilinea[]) => void;
  etiquetaGuardar?: string;
  guardando?: boolean;
}) {
  const [lineas, setLineas] = useState<LineaMultilinea[]>([
    filaVacia(),
    filaVacia(),
  ]);
  const [sugerencias, setSugerencias] = useState<CuentaSugerida[]>([]);
  const [error, setError] = useState<string | null>(null);
  const acabaDeSeleccionar = useRef(false);
  const filaRefs = useRef<Array<HTMLDivElement | null>>([]);

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

  function setFila(indice: number, parche: Partial<LineaMultilinea>) {
    setLineas((prev) => prev.map((l, i) => (i === indice ? { ...l, ...parche } : l)));
    setError(null);
  }

  function anadirFila(indice: number) {
    setLineas((prev) => [...prev.slice(0, indice + 1), filaVacia(), ...prev.slice(indice + 1)]);
    setTimeout(() => {
      const contenedor = filaRefs.current[indice + 1];
      contenedor?.querySelector<HTMLInputElement>("input")?.focus();
    }, 0);
  }

  function quitarFila(indice: number) {
    setLineas((prev) => (prev.length > 2 ? prev.filter((_, i) => i !== indice) : prev));
  }

  function manejarTeclado(e: React.KeyboardEvent<HTMLDivElement>, indice: number) {
    if (e.key === "Enter" && acabaDeSeleccionar.current) {
      acabaDeSeleccionar.current = false;
      e.preventDefault();
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      anadirFila(indice);
      return;
    }
    if (e.ctrlKey && (e.key === "Delete" || e.key === "Backspace")) {
      e.preventDefault();
      quitarFila(indice);
    }
  }

  const { totalDebe, totalHaber, diferencia, cuadra } = useMemo(() => {
    const debe = lineas.reduce((s, l) => s + (Number(l.debe) || 0), 0);
    const haber = lineas.reduce((s, l) => s + (Number(l.haber) || 0), 0);
    return {
      totalDebe: debe,
      totalHaber: haber,
      diferencia: debe - haber,
      cuadra: lineas.length >= 2 && debe > 0 && Math.abs(debe - haber) < 0.0001,
    };
  }, [lineas]);

  return (
    <div className="flex flex-col gap-3">
      {lineas.map((linea, i) => (
        <div
          key={i}
          ref={(el) => {
            filaRefs.current[i] = el;
          }}
          className="flex gap-2 items-end"
          onKeyDown={(e) => manejarTeclado(e, i)}
        >
          <div className="flex-1">
            <AccountAutocomplete
              value={linea.cuentaId}
              onChange={(cuenta) => {
                acabaDeSeleccionar.current = Boolean(cuenta);
                setFila(i, {
                  cuentaId: cuenta ? String(cuenta.id) : "",
                  cuentaCodigo: cuenta ? cuenta.code : "",
                });
              }}
              onSearch={buscar}
              sugerencias={sugerencias}
              placeholder="Cuenta (código)…"
            />
          </div>
          <label className="flex flex-col gap-1">
            Debe
            <input
              inputMode="decimal"
              value={linea.debe}
              onChange={(e) => setFila(i, { debe: e.target.value })}
              className="border rounded px-2 py-1 w-28 font-mono"
            />
          </label>
          <label className="flex flex-col gap-1">
            Haber
            <input
              inputMode="decimal"
              value={linea.haber}
              onChange={(e) => setFila(i, { haber: e.target.value })}
              className="border rounded px-2 py-1 w-28 font-mono"
            />
          </label>
          <label className="flex flex-col gap-1 flex-1">
            Detalle
            <input
              value={linea.detalle}
              onChange={(e) => setFila(i, { detalle: e.target.value })}
              className="border rounded px-2 py-1"
            />
          </label>
          <CentroSelect
            value={linea.centroId}
            onChange={(centroId) => setFila(i, { centroId })}
            soloHojas
          />
          <button
            type="button"
            onClick={() => quitarFila(i)}
            className="rounded px-2 py-1 border"
            aria-label={`Quitar línea ${i + 1}`}
          >
            ✕
          </button>
        </div>
      ))}
      {error && <p className="text-red-600">{error}</p>}
      <div className="flex gap-3 items-center">
        <button
          type="button"
          onClick={() => anadirFila(lineas.length - 1)}
          className="rounded px-3 py-1 border"
        >
          Añadir línea (Enter)
        </button>
        <button
          type="button"
          onClick={() => quitarFila(lineas.length - 1)}
          className="rounded px-3 py-1 border text-red-700"
        >
          Quitar última (Ctrl+Supr)
        </button>
        <span className={cuadra ? "text-emerald-700" : "text-amber-700"}>
          Debe {totalDebe.toFixed(4)} · Haber {totalHaber.toFixed(4)} ·{" "}
          {cuadra ? "Cuadra" : `Diferencia ${diferencia.toFixed(4)}`}
        </span>
        <button
          type="button"
          disabled={!cuadra || guardando}
          onClick={() => onGuardar(lineas)}
          className="bg-blue-600 text-white rounded px-3 py-1 disabled:opacity-50"
        >
          {etiquetaGuardar}
        </button>
        {onGuardarBorrador && (
          <button
            type="button"
            disabled={!cuadra || guardando}
            onClick={() => onGuardarBorrador(lineas)}
            className="rounded px-3 py-1 border disabled:opacity-50"
          >
            Guardar borrador
          </button>
        )}
      </div>
    </div>
  );
}