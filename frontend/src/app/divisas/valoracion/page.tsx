"use client";

import Link from "next/link";
import { useState } from "react";
import {
  ApiError,
  crearValoracion,
  formatearImporte,
  listarDiferenciasCambio,
  type ValoracionItem,
} from "@/components/forex/api";

interface DiferenciaItem extends ValoracionItem {
  id: string;
  fecha_valoracion: string;
  estado: string;
  asiento_id: string | null;
}

export default function ValoracionPage() {
  const [ejercicio, setEjercicio] = useState(String(new Date().getFullYear()));
  const [fecha, setFecha] = useState(`${new Date().getFullYear()}-12-31`);
  const [resultado, setResultado] = useState<{ n: number; asiento_id: string | null } | null>(
    null
  );
  const [items, setItems] = useState<DiferenciaItem[]>([]);
  const [aviso, setAviso] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);

  async function ejecutar() {
    setCargando(true);
    setAviso(null);
    setResultado(null);
    try {
      const res = await crearValoracion(Number(ejercicio), fecha);
      setResultado({ n: res.n, asiento_id: res.asiento_id });
      await listar();
    } catch (error) {
      setAviso(error instanceof ApiError ? error.message : "Error en la valoración");
    } finally {
      setCargando(false);
    }
  }

  async function listar() {
    setAviso(null);
    try {
      const res = await listarDiferenciasCambio({ ejercicio: Number(ejercicio) || undefined });
      setItems(res.items);
    } catch (error) {
      setAviso(error instanceof ApiError ? error.message : "No se pudieron listar diferencias");
    }
  }

  return (
    <main className="p-6 max-w-4xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">
        Valoración de saldos en divisa{" "}
        <Link className="text-sm text-blue-600 underline" href="/divisas">
          divisas
        </Link>
      </h1>

      <section className="border rounded p-4 mb-4">
        <h2 className="font-medium mb-2">Cierre de diferencias de cambio</h2>
        <div className="grid grid-cols-2 gap-3 mb-3">
          <label className="block">
            Ejercicio
            <input
              type="number"
              className="w-full border rounded p-1"
              value={ejercicio}
              onChange={(e) => setEjercicio(e.target.value)}
            />
          </label>
          <label className="block">
            Fecha de valoración
            <input
              type="date"
              className="w-full border rounded p-1"
              value={fecha}
              onChange={(e) => setFecha(e.target.value)}
            />
          </label>
        </div>
        <button
          className="bg-blue-600 text-white rounded px-3 py-1"
          onClick={ejecutar}
          disabled={cargando}
        >
          {cargando ? "Valorando…" : "Ejecutar valoración"}
        </button>
        {aviso && <p className="mt-2 text-sm text-amber-700">{aviso}</p>}
        {resultado && (
          <p className="mt-2 text-sm text-green-700">
            {resultado.n} diferencias{" "}
            {resultado.asiento_id ? `· asiento ${resultado.asiento_id}` : "(sin saldos)"}
          </p>
        )}
      </section>

      <section className="border rounded p-4">
        <h2 className="font-medium mb-2">Diferencias de cambio</h2>
        <button className="mb-2 bg-slate-800 text-white rounded px-3 py-1" onClick={listar}>
          Consultar
        </button>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left border-b">
              <th>Cuenta</th>
              <th>Divisa</th>
              <th>Saldo divisa</th>
              <th>Funcional previo</th>
              <th>Diferencia</th>
              <th>Tipo</th>
              <th>Estado</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id} className="border-b">
                <td>{item.cuenta}</td>
                <td>{item.divisa}</td>
                <td>{formatearImporte(item.saldo_divisa)}</td>
                <td>{formatearImporte(item.saldo_funcional_previo)}</td>
                <td>{formatearImporte(item.diferencia)}</td>
                <td>{item.tipo}</td>
                <td>{item.estado}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}