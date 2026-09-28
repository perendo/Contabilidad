"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../../../components/treasury/api";
import { get, post } from "../../../services/client";

interface Movimiento {
  id: string;
  concepto: string;
  importe: string;
  signo: string;
}

interface Apunte {
  id: string;
  cuenta: string;
  debe: string;
  haber: string;
  descripcion: string | null;
}

interface Informe {
  id: string;
  estado: string;
  saldo_banco: string;
  saldo_libros: string;
  diferencia: string;
  pendientes: {
    movimientos_sin_cruzar: Movimiento[];
    apuntes_sin_extracto: Apunte[];
  };
}

interface Propuesta {
  id: string;
  movimiento_id: string;
  apunte_id: string;
  importe: string;
  prioridad: string;
}

export default function DetalleConciliacionPage() {
  const params = useParams<{ id: string }>();
  const [informe, setInforme] = useState<Informe | null>(null);
  const [propuestas, setPropuestas] = useState<Propuesta[]>([]);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setError(null);
    try {
      setInforme(await get<Informe>(`/api/v1/conciliaciones/${params.id}`));
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }, [params.id]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  async function proponer() {
    try {
      const cuerpo = await post<{ propuestas: Propuesta[] }>(
        `/api/v1/conciliaciones/${params.id}/propuestas`
      );
      setPropuestas(cuerpo.propuestas);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }

  async function confirmar(p: Propuesta) {
    try {
      await post(`/api/v1/conciliaciones/${params.id}/cruces`, {
        cruces: [{ movimiento_id: p.movimiento_id, apunte_id: p.apunte_id, origen: "auto" }],
      });
      setPropuestas((prev) => prev.filter((x) => x.id !== p.id));
      await cargar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }

  async function cerrar() {
    if (!window.confirm("¿Cerrar y archivar la conciliación?")) return;
    try {
      await post(`/api/v1/conciliaciones/${params.id}/cerrar`);
      await cargar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }

  return (
    <main className="p-6 max-w-4xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Conciliación</h1>
      {error && <p className="text-red-600 mb-4">{error}</p>}
      {informe && (
        <>
          <p className="mb-2 text-sm">
            Saldo banco <span className="font-mono">{informe.saldo_banco}</span> · Libros{" "}
            <span className="font-mono">{informe.saldo_libros}</span> · Diferencia{" "}
            <span className={informe.diferencia === "0.0000" ? "text-emerald-700" : "text-amber-700"}>
              <span className="font-mono">{informe.diferencia}</span>
            </span>{" "}
            · {informe.estado}
          </p>
          <div className="flex gap-3 mb-4">
            <button onClick={proponer} className="bg-slate-800 text-white rounded px-3 py-1">
              Generar propuestas
            </button>
            <button
              onClick={cerrar}
              disabled={informe.estado === "cerrada"}
              className="bg-blue-600 text-white rounded px-3 py-1 disabled:opacity-50"
            >
              Cerrar y archivar
            </button>
          </div>
          {propuestas.length > 0 && (
            <>
              <h2 className="font-semibold mb-2">Propuestas</h2>
              <table className="w-full border-collapse text-sm mb-6">
                <thead>
                  <tr className="border-b">
                    <th className="text-right p-2">Importe</th>
                    <th className="text-left p-2">Prioridad</th>
                    <th className="p-2" />
                  </tr>
                </thead>
                <tbody>
                  {propuestas.map((p) => (
                    <tr key={p.id} className="border-b">
                      <td className="text-right p-2 font-mono">{p.importe}</td>
                      <td className="p-2">{p.prioridad}</td>
                      <td className="p-2 text-right">
                        <button onClick={() => confirmar(p)} className="text-blue-700 underline">
                          Confirmar
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
          <h2 className="font-semibold mb-2">Pendientes</h2>
          <p className="text-sm mb-1">
            Movimientos sin cruzar: {informe.pendientes.movimientos_sin_cruzar.length}
          </p>
          <p className="text-sm">
            Apuntes sin extracto: {informe.pendientes.apuntes_sin_extracto.length}
          </p>
        </>
      )}
    </main>
  );
}
