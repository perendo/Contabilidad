"use client";

import { useCallback, useEffect, useState } from "react";

import {
  formatearImporte,
  obtener303,
  obtener347,
  obtener349,
  type Modelo303,
  type Modelo347,
  type Modelo349,
} from "../../components/vat/api";
import { ApiError } from "../../components/treasury/api";

type Pestana = "303" | "347" | "349";

export default function ModelosPage() {
  const [pestana, setPestana] = useState<Pestana>("303");
  const [ejercicio, setEjercicio] = useState(2026);
  const [periodo, setPeriodo] = useState(1);
  const [tipoPeriodo, setTipoPeriodo] = useState("TRIMESTRE");
  const [m303, setM303] = useState<Modelo303 | null>(null);
  const [m347, setM347] = useState<Modelo347 | null>(null);
  const [m349, setM349] = useState<Modelo349 | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setError(null);
    try {
      if (pestana === "303") setM303(await obtener303(ejercicio, periodo, tipoPeriodo));
      if (pestana === "347") setM347(await obtener347(ejercicio));
      if (pestana === "349") setM349(await obtener349(ejercicio, periodo, tipoPeriodo));
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }, [pestana, ejercicio, periodo, tipoPeriodo]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  return (
    <main className="p-6 max-w-4xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Modelos fiscales</h1>
      <div className="flex items-end gap-3 mb-4">
        {(["303", "347", "349"] as Pestana[]).map((p) => (
          <button
            key={p}
            onClick={() => setPestana(p)}
            className={`rounded px-3 py-1 ${
              pestana === p ? "bg-blue-600 text-white" : "bg-gray-200"
            }`}
          >
            {p}
          </button>
        ))}
        <label className="block">
          <span className="text-sm">Ejercicio</span>
          <input
            type="number"
            value={ejercicio}
            onChange={(e) => setEjercicio(Number(e.target.value))}
            className="border rounded px-2 py-1 mt-1 w-24"
          />
        </label>
        <label className="block">
          <span className="text-sm">Periodo</span>
          <input
            type="number"
            value={periodo}
            onChange={(e) => setPeriodo(Number(e.target.value))}
            className="border rounded px-2 py-1 mt-1 w-16"
          />
        </label>
        <select
          value={tipoPeriodo}
          onChange={(e) => setTipoPeriodo(e.target.value)}
          className="border rounded px-2 py-1"
        >
          <option value="TRIMESTRE">TRIMESTRE</option>
          <option value="MES">MES</option>
        </select>
      </div>

      {error && <p className="text-red-600 mb-4">{error}</p>}

      <div className="border rounded p-4">
        {pestana === "303" && m303 && (
          <div className="text-sm">
            <p className="mb-2">
              Cuadre con libros:{" "}
              <strong className={m303.cuadre_libros ? "text-emerald-700" : "text-red-600"}>
                {m303.cuadre_libros ? "correcto" : "descuadrado"}
              </strong>
            </p>
            <p>Devengado: {JSON.stringify(m303.devengado)}</p>
            <p>Deducible: {JSON.stringify(m303.deducible)}</p>
            <p>Recargo equivalencia: {formatearImporte(m303.recargo_equivalencia.cuota)}</p>
            <p>
              Resultado a ingresar: {formatearImporte(m303.resultado.a_ingresar)} · a
              compensar: {formatearImporte(m303.resultado.a_compensar)}
            </p>
            <p>IVA diferido pendiente: {formatearImporte(m303.iva_diferido.pendiente)}</p>
          </div>
        )}
        {pestana === "347" && m347 && (
          <table className="w-full text-sm">
            <thead className="bg-gray-100">
              <tr>
                <th className="text-left p-2">NIF</th>
                <th className="text-left p-2">Nombre</th>
                <th className="text-left p-2">Clave</th>
                <th className="text-right p-2">Importe</th>
                <th className="text-right p-2">Nº</th>
              </tr>
            </thead>
            <tbody>
              {m347.operaciones.map((op) => (
                <tr key={op.nif_tercero} className="border-t">
                  <td className="p-2">{op.nif_tercero}</td>
                  <td className="p-2">{op.nombre}</td>
                  <td className="p-2">{op.clave_operacion}</td>
                  <td className="p-2 text-right">{formatearImporte(op.importe_acumulado)}</td>
                  <td className="p-2 text-right">{op.n_operaciones}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {pestana === "349" && m349 && (
          <div className="text-sm">
            <p className="mb-2">Total: {formatearImporte(m349.total_general)}</p>
            <table className="w-full">
              <thead className="bg-gray-100">
                <tr>
                  <th className="text-left p-2">NIF</th>
                  <th className="text-left p-2">Clave</th>
                  <th className="text-left p-2">Tipo</th>
                  <th className="text-right p-2">Importe</th>
                </tr>
              </thead>
              <tbody>
                {m349.operaciones.map((op) => (
                  <tr key={`${op.nif_tercero}-${op.clave_operacion}`} className="border-t">
                    <td className="p-2">{op.nif_tercero}</td>
                    <td className="p-2">{op.clave_operacion}</td>
                    <td className="p-2">{op.tipo_operacion}</td>
                    <td className="p-2 text-right">{formatearImporte(op.importe)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </main>
  );
}