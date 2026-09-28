"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ApiError,
  crearTipo,
  listarDivisas,
  listarTipos,
  type Divisa,
  type TipoCambio,
} from "@/components/forex/api";

export default function TiposPage() {
  const [divisas, setDivisas] = useState<Divisa[]>([]);
  const [divisaId, setDivisaId] = useState("");
  const [fecha, setFecha] = useState("2026-10-01");
  const [ratio, setRatio] = useState("1.08500000");
  const [tipos, setTipos] = useState<TipoCambio[]>([]);
  const [filtroDivisa, setFiltroDivisa] = useState("");
  const [aviso, setAviso] = useState<string | null>(null);

  async function refrescarDivisas() {
    try {
      const datos = await listarDivisas();
      setDivisas(datos.items);
      if (datos.items.length > 0) setDivisaId(datos.items[0].id);
    } catch (error) {
      setAviso(error instanceof ApiError ? error.message : "No se pudieron cargar divisas");
    }
  }

  async function refrescarTipos() {
    setAviso(null);
    try {
      const filtros: { divisa_id?: string } = {};
      if (filtroDivisa) filtros.divisa_id = filtroDivisa;
      setTipos((await listarTipos(filtros)).items);
    } catch (error) {
      setAviso(error instanceof ApiError ? error.message : "No se pudieron cargar tipos");
    }
  }

  useEffect(() => {
    refrescarDivisas();
  }, []);

  async function alta() {
    setAviso(null);
    try {
      await crearTipo(divisaId, fecha, ratio);
      setRatio("1.00000000");
      await refrescarTipos();
    } catch (error) {
      setAviso(error instanceof ApiError ? error.message : "Error al crear el tipo");
    }
  }

  return (
    <main className="p-6 max-w-4xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">
        Tipos de cambio{" "}
        <Link className="text-sm text-blue-600 underline" href="/divisas/tipos/historial">
          historial
        </Link>
      </h1>

      <section className="border rounded p-4 mb-4">
        <h2 className="font-medium mb-2">Nuevo tipo</h2>
        <div className="grid grid-cols-3 gap-3">
          <label className="block">
            Divisa
            <select
              className="w-full border rounded p-1"
              value={divisaId}
              onChange={(e) => setDivisaId(e.target.value)}
            >
              {divisas.map((divisa) => (
                <option key={divisa.id} value={divisa.id}>
                  {divisa.codigo_iso}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            Fecha
            <input
              type="date"
              className="w-full border rounded p-1"
              value={fecha}
              onChange={(e) => setFecha(e.target.value)}
            />
          </label>
          <label className="block">
            Ratio (1 divisa = X funcional)
            <input
              className="w-full border rounded p-1"
              value={ratio}
              onChange={(e) => setRatio(e.target.value)}
            />
          </label>
        </div>
        <button
          className="mt-3 bg-blue-600 text-white rounded px-3 py-1"
          onClick={alta}
          disabled={!divisaId}
        >
          Registrar tipo
        </button>
        {aviso && <p className="mt-2 text-sm text-amber-700">{aviso}</p>}
      </section>

      <section className="border rounded p-4 mb-4">
        <h2 className="font-medium mb-2">Tipos registrados</h2>
        <div className="mb-2 flex gap-2">
          <select
            className="border rounded p-1"
            value={filtroDivisa}
            onChange={(e) => {
              setFiltroDivisa(e.target.value);
              refrescarTipos();
            }}
          >
            <option value="">Todas las divisas</option>
            {divisas.map((divisa) => (
              <option key={divisa.id} value={divisa.id}>
                {divisa.codigo_iso}
              </option>
            ))}
          </select>
          <button
            className="bg-slate-800 text-white rounded px-3 py-1"
            onClick={refrescarTipos}
          >
            Consultar
          </button>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left border-b">
              <th>Divisa</th>
              <th>Fecha</th>
              <th>Ratio</th>
              <th>Usos</th>
              <th>Estado</th>
            </tr>
          </thead>
          <tbody>
            {tipos.map((tipo) => (
              <tr key={tipo.id} className="border-b">
                <td>{tipo.divisa}</td>
                <td>{tipo.fecha}</td>
                <td>{tipo.ratio}</td>
                <td>{tipo.usos_posteados}</td>
                <td>{tipo.sellado ? "sellado" : "editable"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}