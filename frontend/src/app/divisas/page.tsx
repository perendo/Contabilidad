"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, crearDivisa, listarDivisas, type ListaDivisas } from "../../components/forex/api";

export default function DivisasPage() {
  const [datos, setDatos] = useState<ListaDivisas | null>(null);
  const [nuevoCodigo, setNuevoCodigo] = useState("");
  const [aviso, setAviso] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);

  async function refrescar() {
    setCargando(true);
    setAviso(null);
    try {
      setDatos(await listarDivisas());
    } catch (error) {
      setAviso(error instanceof ApiError ? error.message : "No se pudieron cargar las divisas");
    } finally {
      setCargando(false);
    }
  }

  useEffect(() => {
    refrescar();
  }, []);

  async function alta() {
    setAviso(null);
    try {
      await crearDivisa(nuevoCodigo.toUpperCase());
      setNuevoCodigo("");
      await refrescar();
    } catch (error) {
      setAviso(error instanceof ApiError ? error.message : "Error al crear la divisa");
    }
  }

  return (
    <main className="p-6 max-w-4xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Multi-divisa</h1>
      <nav className="mb-4 flex gap-4 text-sm">
        <Link className="text-blue-600 underline" href="/divisas/tipos">
          Tipos de cambio
        </Link>
        <Link className="text-blue-600 underline" href="/divisas/tipos/historial">
          Historial de tipos
        </Link>
        <Link className="text-blue-600 underline" href="/divisas/asientos/nuevo">
          Nuevo asiento en divisa
        </Link>
        <Link className="text-blue-600 underline" href="/divisas/valoracion">
          Valoración de saldos
        </Link>
      </nav>

      <section className="border rounded p-4 mb-4">
        <h2 className="font-medium mb-2">
          Divisa funcional: {datos?.funcional ?? "EUR"}
        </h2>
        <div className="grid gap-2 mb-3">
          {datos?.items.map((divisa) => (
            <div key={divisa.id} className="flex justify-between border-b py-1">
              <span>{divisa.codigo_iso}</span>
              <span className="text-sm text-slate-500">
                {divisa.activa ? "activa" : "inactiva"}
              </span>
            </div>
          ))}
        </div>
      </section>

      <section className="border rounded p-4 mb-4">
        <h2 className="font-medium mb-2">Nueva divisa de trabajo</h2>
        <div className="flex gap-2">
          <input
            className="border rounded p-1"
            value={nuevoCodigo}
            onChange={(e) => setNuevoCodigo(e.target.value.toUpperCase())}
            maxLength={3}
            placeholder="USD"
          />
          <button
            className="bg-blue-600 text-white rounded px-3 py-1"
            onClick={alta}
            disabled={nuevoCodigo.length !== 3 || cargando}
          >
            Crear divisa
          </button>
        </div>
        {aviso && <p className="mt-2 text-sm text-amber-700">{aviso}</p>}
      </section>
    </main>
  );
}