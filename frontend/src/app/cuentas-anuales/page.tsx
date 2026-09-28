"use client";

import { useCallback, useEffect, useState } from "react";

import { BalanceView } from "../../components/reporting/BalanceView";
import { EfeView } from "../../components/reporting/EfeView";
import { PygView } from "../../components/reporting/PygView";
import {
  anularFormulacion,
  formular,
  listarFormulaciones,
  obtenerBalance,
  obtenerEfe,
  obtenerPyg,
  type BalanceReport,
  type EfeReport,
  type Formulacion,
  type PygReport,
} from "../../components/reporting/api";
import { ApiError } from "../../components/treasury/api";

type Pestana = "balance" | "pyg" | "efe";

export default function CuentasAnualesPage() {
  const [ejercicio, setEjercicio] = useState(2026);
  const [pestana, setPestana] = useState<Pestana>("balance");
  const [modo, setModo] = useState("provisional");
  const [balance, setBalance] = useState<BalanceReport | null>(null);
  const [pyg, setPyg] = useState<PygReport | null>(null);
  const [efe, setEfe] = useState<EfeReport | null>(null);
  const [formulaciones, setFormulaciones] = useState<Formulacion[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const cargar = useCallback(async () => {
    setError(null);
    try {
      if (pestana === "balance") setBalance(await obtenerBalance(ejercicio, { modo }));
      if (pestana === "pyg") setPyg(await obtenerPyg(ejercicio, { modo }));
      if (pestana === "efe") setEfe(await obtenerEfe(ejercicio, { modo }));
      setFormulaciones((await listarFormulaciones(ejercicio)).items);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }, [ejercicio, pestana, modo]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  async function ejecutar(accion: () => Promise<unknown>) {
    setError(null);
    setOcupado(true);
    try {
      await accion();
      await cargar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    } finally {
      setOcupado(false);
    }
  }

  const vigente = formulaciones.find((f) => f.estado === "formulada") ?? null;

  return (
    <main className="p-6 max-w-4xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Cuentas anuales</h1>

      <div className="flex items-end gap-4 mb-4">
        <label className="block">
          <span className="text-sm">Ejercicio</span>
          <input
            type="number"
            value={ejercicio}
            onChange={(e) => setEjercicio(Number(e.target.value))}
            className="border rounded px-3 py-1 mt-1 w-32"
          />
        </label>
        <label className="block">
          <span className="text-sm">Modo</span>
          <select
            value={modo}
            onChange={(e) => setModo(e.target.value)}
            className="border rounded px-2 py-1 mt-1"
          >
            <option value="provisional">provisional</option>
            <option value="oficial">oficial</option>
          </select>
        </label>
        <div className="flex gap-2">
          {(["balance", "pyg", "efe"] as Pestana[]).map((p) => (
            <button
              key={p}
              onClick={() => setPestana(p)}
              className={`rounded px-3 py-1 ${
                pestana === p ? "bg-blue-600 text-white" : "bg-gray-200"
              }`}
            >
              {p.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="text-red-600 mb-4">{error}</p>}

      <div className="border rounded p-4 mb-6">
        {pestana === "balance" &&
          (balance ? <BalanceView report={balance} /> : <p>Cargando…</p>)}
        {pestana === "pyg" && (pyg ? <PygView report={pyg} /> : <p>Cargando…</p>)}
        {pestana === "efe" && (efe ? <EfeView report={efe} /> : <p>Cargando…</p>)}
      </div>

      <div className="flex gap-3 mb-4">
        <button
          onClick={() => ejecutar(() => formular(ejercicio, "Formulación anual"))}
          disabled={ocupado || vigente !== null}
          className="bg-emerald-600 text-white rounded px-4 py-2 disabled:opacity-50"
        >
          Formular cuentas anuales
        </button>
        <button
          onClick={() => {
            const motivo = window.prompt("Motivo de anulación");
            if (motivo) ejecutar(() => anularFormulacion(ejercicio, motivo));
          }}
          disabled={ocupado || vigente === null}
          className="bg-red-600 text-white rounded px-4 py-2 disabled:opacity-50"
        >
          Anular formulación
        </button>
      </div>

      <h2 className="font-medium mb-2">Histórico de formulaciones</h2>
      <table className="w-full text-sm border">
        <thead className="bg-gray-100">
          <tr>
            <th className="text-left p-2">Nº</th>
            <th className="text-left p-2">Fecha</th>
            <th className="text-left p-2">Estado</th>
            <th className="text-left p-2">Hash</th>
          </tr>
        </thead>
        <tbody>
          {formulaciones.map((f) => (
            <tr key={f.formulacion_id} className="border-t">
              <td className="p-2">{f.numero_formulacion}</td>
              <td className="p-2">{f.fecha_formulacion.slice(0, 19)}</td>
              <td className="p-2">{f.estado}</td>
              <td className="p-2 font-mono text-xs">{f.contenido_hash.slice(0, 12)}…</td>
            </tr>
          ))}
          {formulaciones.length === 0 && (
            <tr>
              <td className="p-2 text-gray-500" colSpan={4}>
                (sin formulaciones)
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </main>
  );
}