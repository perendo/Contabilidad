"use client";

import { useState } from "react";

import {
  AccountAutocomplete,
  type CuentaSugerida,
} from "../../../components/acct/AccountAutocomplete";
import { ApiError } from "../../../components/treasury/api";
import { get } from "../../../services/client";
import LedgerTable from "../../../components/reports/LedgerTable";

interface Mayor {
  cuenta: { id: number; code: string; name: string };
  saldo_inicial: string;
  movimientos: {
    fecha: string;
    numero: number | null;
    concepto: string;
    debe: string;
    haber: string;
    saldo_acumulado: string;
  }[];
  saldo_final: string;
}

interface Sugerencias {
  items: CuentaSugerida[];
}

export default function MayorPage() {
  const [cuentaId, setCuentaId] = useState("");
  const [sugerencias, setSugerencias] = useState<CuentaSugerida[]>([]);
  const [mayor, setMayor] = useState<Mayor | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);

  async function buscar(query: string) {
    if (!query.trim()) {
      setSugerencias([]);
      return;
    }
    try {
      const params = new URLSearchParams({ q: query, limit: "20" });
      const cuerpo = await get<Sugerencias>(`/api/v1/accounts/suggest?${params}`);
      setSugerencias(cuerpo.items);
    } catch {
      setSugerencias([]);
    }
  }

  async function consultar(evento: React.FormEvent) {
    evento.preventDefault();
    setError(null);
    setCargando(true);
    try {
      setMayor(await get<Mayor>(`/api/v1/reports/ledger/${cuentaId}`));
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    } finally {
      setCargando(false);
    }
  }

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Libro mayor</h1>
      <form onSubmit={consultar} className="flex gap-3 mb-4 items-end">
        <div className="flex flex-col gap-1">
          <span>Subcuenta</span>
          <AccountAutocomplete
            value={cuentaId}
            onChange={(cuenta) => setCuentaId(cuenta ? String(cuenta.id) : "")}
            onSearch={buscar}
            sugerencias={sugerencias}
          />
        </div>
        <button type="submit" disabled={cargando || !cuentaId} className="bg-blue-600 text-white rounded px-3 py-1 disabled:opacity-50">
          {cargando ? "Consultando…" : "Consultar"}
        </button>
      </form>
      {error && <p className="text-red-600 mb-4">{error}</p>}
      {mayor && (
        <>
          <p className="mb-2">
            {mayor.cuenta.code} {mayor.cuenta.name} · Saldo final{" "}
            <span className="font-mono">{mayor.saldo_final}</span>
          </p>
          <LedgerTable movimientos={mayor.movimientos} />
        </>
      )}
    </main>
  );
}
