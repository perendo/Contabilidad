"use client";

import { useEffect, useState } from "react";
import { PlanTree } from "@/components/acct/PlanTree";
import { obtenerArbolCuentas, type CuentaNodo } from "@/services/acct/api";

export default function CuentasPage() {
  const [nodos, setNodos] = useState<CuentaNodo[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function cargarArbol() {
      try {
        setCargando(true);
        const data = await obtenerArbolCuentas();
        setNodos(data.nodos || []);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Error al cargar el plan de cuentas");
      } finally {
        setCargando(false);
      }
    }
    cargarArbol();
  }, []);

  if (cargando) {
    return (
      <div className="p-4 text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
        <p className="mt-2 text-gray-600">Cargando plan de cuentas...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 text-center text-red-600">
        <p>{error}</p>
      </div>
    );
  }

  return (
    <div className="p-4">
      <h1 className="text-2xl font-bold mb-4">Plan General Contable</h1>
      <div className="bg-white rounded-lg shadow border">
        <PlanTree nodos={nodos} />
      </div>
    </div>
  );
}