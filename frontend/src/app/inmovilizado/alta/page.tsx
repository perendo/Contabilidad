"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  obtenerArbolCuentas,
  type CuentaNodo,
} from "../../../services/acct/api";
import {
  ApiError,
  calcularPlan,
  crearActivo,
  type Activo,
  type DatosPlan,
  type FilaPlan,
} from "../../../components/inmovilizado/api";

interface CuentaPlana {
  id: string;
  code: string;
  name: string;
}

function aplanar(nodos: CuentaNodo[]): CuentaPlana[] {
  const salida: CuentaPlana[] = [];
  for (const n of nodos) {
    if (n.is_selectable && n.code.startsWith("2")) {
      salida.push({ id: n.id, code: n.code, name: n.name });
    }
    salida.push(...aplanar(n.children));
  }
  return salida;
}

export default function AltaActivoPage() {
  const [form, setForm] = useState<DatosPlan>({
    numero_activo: "",
    cuenta_id: 0,
    descripcion: "",
    fecha_alta: "2026-01-01",
    coste_amortizable: "15000.0000",
    vida_util: 60,
    metodo: "lineal",
    porcentaje_regresivo: null,
  });
  const [cuentas, setCuentas] = useState<CuentaPlana[]>([]);
  const [plan, setPlan] = useState<FilaPlan[] | null>(null);
  const [creado, setCreado] = useState<Activo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState<string | null>(null);

  useEffect(() => {
    obtenerArbolCuentas()
      .then((r) => setCuentas(aplanar(r.nodos)))
      .catch(() => setCuentas([]));
  }, []);

  const set = (campo: string, valor: unknown) =>
    setForm((f) => ({ ...f, [campo]: valor }));

  const previsualizar = useCallback(async () => {
    setError(null);
    setPlan(null);
    setOcupado("preview");
    try {
      const r = await calcularPlan(form);
      setPlan(r.plan);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    } finally {
      setOcupado(null);
    }
  }, [form]);

  const guardar = useCallback(async () => {
    setError(null);
    setCreado(null);
    setOcupado("crear");
    try {
      const r = await crearActivo({ ...form, cuenta_id: Number(form.cuenta_id) });
      setCreado(r);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    } finally {
      setOcupado(null);
    }
  }, [form]);

  return (
    <main className="p-6 max-w-3xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Alta de activo fijo</h1>

      <div className="grid grid-cols-2 gap-4 text-sm">
        <label className="block">
          <span>Nº de activo</span>
          <input
            className="border rounded px-3 py-1 mt-1 w-full"
            value={form.numero_activo}
            onChange={(e) => set("numero_activo", e.target.value)}
          />
        </label>
        <label className="block">
          <span>Cuenta contable (nivel 4)</span>
          <select
            className="border rounded px-3 py-1 mt-1 w-full"
            value={form.cuenta_id || ""}
            onChange={(e) => set("cuenta_id", Number(e.target.value))}
          >
            <option value="">Selecciona…</option>
            {cuentas.map((c) => (
              <option key={c.id} value={c.id}>
                {c.code} · {c.name}
              </option>
            ))}
          </select>
        </label>
        <label className="block col-span-2">
          <span>Descripción</span>
          <input
            className="border rounded px-3 py-1 mt-1 w-full"
            value={form.descripcion}
            onChange={(e) => set("descripcion", e.target.value)}
          />
        </label>
        <label className="block">
          <span>Fecha de alta</span>
          <input
            type="date"
            className="border rounded px-3 py-1 mt-1 w-full"
            value={form.fecha_alta}
            onChange={(e) => set("fecha_alta", e.target.value)}
          />
        </label>
        <label className="block">
          <span>Coste amortizable</span>
          <input
            className="border rounded px-3 py-1 mt-1 w-full font-mono"
            value={form.coste_amortizable}
            onChange={(e) => set("coste_amortizable", e.target.value)}
          />
        </label>
        <label className="block">
          <span>Vida útil (meses)</span>
          <input
            type="number"
            className="border rounded px-3 py-1 mt-1 w-full"
            value={form.vida_util}
            onChange={(e) => set("vida_util", Number(e.target.value))}
          />
        </label>
        <label className="block">
          <span>Método</span>
          <select
            className="border rounded px-3 py-1 mt-1 w-full"
            value={form.metodo}
            onChange={(e) => {
              set("metodo", e.target.value);
              if (e.target.value === "lineal") set("porcentaje_regresivo", null);
            }}
          >
            <option value="lineal">Lineal</option>
            <option value="regresivo">Regresivo (porcentaje)</option>
          </select>
        </label>
        {form.metodo === "regresivo" && (
          <label className="block">
            <span>Porcentaje regresivo (%)</span>
            <input
              className="border rounded px-3 py-1 mt-1 w-full"
              value={form.porcentaje_regresivo ?? ""}
              onChange={(e) => set("porcentaje_regresivo", e.target.value)}
            />
          </label>
        )}
      </div>

      {error && <p className="text-red-600 my-4">{error}</p>}

      <div className="flex gap-3 mt-4">
        <button
          onClick={previsualizar}
          disabled={ocupado !== null}
          className="bg-gray-200 rounded px-4 py-2 disabled:opacity-50"
        >
          {ocupado === "preview" ? "Calculando…" : "Previsualizar plan"}
        </button>
        <button
          onClick={guardar}
          disabled={ocupado !== null}
          className="bg-blue-600 text-white rounded px-4 py-2 disabled:opacity-50"
        >
          {ocupado === "crear" ? "Guardando…" : "Guardar activo"}
        </button>
      </div>

      {plan && (
        <div className="border rounded p-4 mt-6 text-sm max-h-80 overflow-auto">
          <h2 className="font-semibold mb-2">
            Plan de amortización ({plan.length} períodos)
          </h2>
          <table className="w-full">
            <thead>
              <tr className="text-left text-gray-500">
                <th className="p-1">Período</th>
                <th className="p-1">Cuota</th>
                <th className="p-1">Acumulado</th>
              </tr>
            </thead>
            <tbody>
              {plan.map((f, i) => (
                <tr key={i} className="border-t">
                  <td className="p-1 font-mono">
                    {f.ejercicio}-{String(f.periodo).padStart(2, "0")}
                  </td>
                  <td className="p-1 font-mono">{f.cuota}</td>
                  <td className="p-1 font-mono">{f.acumulado}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {creado && (
        <div className="border rounded p-4 mt-6 text-sm bg-green-50">
          <p>
            Activo{" "}
            <span className="font-mono">{creado.numero_activo}</span> dado de alta.
          </p>
          <Link className="text-blue-600 underline" href={`/inmovilizado/${creado.id}`}>
            Ver detalle
          </Link>
        </div>
      )}
    </main>
  );
}