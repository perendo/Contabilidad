"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../../components/treasury/api";
import { get, post } from "../../services/client";

interface EstadoApertura {
  ejercicio: number;
  estado: string;
  asiento_apertura_id: string | null;
  asiento_anulacion_id: string | null;
}

interface ResultadoApertura {
  ejercicio: number;
  asiento_id: string;
  numero_asiento: number;
  total_lineas: number;
  importe_total_debe: string;
  estado: string;
  regenerada?: boolean;
}

const ETIQUETA: Record<string, string> = {
  abierto: "Abierto (listo para apertura)",
  cerrado: "Cerrado (apertura pendiente)",
  con_apertura: "Con apertura generada",
  apertura_anulada: "Apertura anulada",
  no_definido: "No definido",
};

export default function AperturaPage() {
  const [ejercicio, setEjercicio] = useState(2027);
  const [estado, setEstado] = useState<EstadoApertura | null>(null);
  const [resultado, setResultado] = useState<ResultadoApertura | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState<string | null>(null);

  const consultar = useCallback(async (anio: number) => {
    setError(null);
    try {
      const cuerpo = await get<EstadoApertura>(
        `/api/v1/ciclo/apertura/estado?ejercicio=${anio}`
      );
      setEstado(cuerpo);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }, []);

  useEffect(() => {
    consultar(ejercicio);
  }, [consultar, ejercicio]);

  async function ejecutar(accion: string, ruta: string, confirmacion?: string) {
    if (confirmacion && !window.confirm(confirmacion)) return;
    setError(null);
    setResultado(null);
    setOcupado(accion);
    try {
      const cuerpo = await post<ResultadoApertura | EstadoApertura>(
        ruta,
        { ejercicio }
      );
      if ("asiento_id" in cuerpo || "regenerada" in cuerpo) {
        setResultado(cuerpo as ResultadoApertura);
      }
      await consultar(ejercicio);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    } finally {
      setOcupado(null);
    }
  }

  return (
    <main className="p-6 max-w-3xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Apertura del ejercicio</h1>
      <div className="flex items-end gap-4 mb-4">
        <label className="block">
          <span className="text-sm">Ejercicio destino</span>
          <input
            type="number"
            value={ejercicio}
            onChange={(e) => setEjercicio(Number(e.target.value))}
            className="border rounded px-3 py-1 mt-1 w-36"
          />
        </label>
        <button
          onClick={() => consultar(ejercicio)}
          className="bg-gray-200 rounded px-3 py-1"
        >
          Consultar estado
        </button>
      </div>

      {error && <p className="text-red-600 mb-4">{error}</p>}

      {estado && (
        <div className="border rounded p-4 mb-6 text-sm">
          <p>
            <strong>Estado:</strong>{" "}
            {ETIQUETA[estado.estado] ?? estado.estado}
          </p>
          {estado.asiento_apertura_id && (
            <p className="font-mono">
              Apertura: {estado.asiento_apertura_id.slice(0, 8)}…
            </p>
          )}
          {estado.asiento_anulacion_id && (
            <p className="font-mono">
              Anulación: {estado.asiento_anulacion_id.slice(0, 8)}…
            </p>
          )}
        </div>
      )}

      <div className="flex gap-3">
        <button
          onClick={() =>
            ejecutar(
              "abrir",
              "/api/v1/ciclo/apertura",
              `Generar el asiento de apertura de ${ejercicio}?`
            )
          }
          disabled={ocupado !== null}
          className="bg-blue-600 text-white rounded px-4 py-2 disabled:opacity-50"
        >
          {ocupado === "abrir" ? "Abriendo…" : "Abrir ejercicio"}
        </button>
        <button
          onClick={() =>
            ejecutar(
              "anular",
              "/api/v1/ciclo/apertura/anular",
              `Anular la apertura de ${ejercicio}?`
            )
          }
          disabled={ocupado !== null}
          className="bg-red-600 text-white rounded px-4 py-2 disabled:opacity-50"
        >
          {ocupado === "anular" ? "Anulando…" : "Anular apertura"}
        </button>
        <button
          onClick={() =>
            ejecutar(
              "regenerar",
              "/api/v1/ciclo/apertura/regenerar",
              `Regenerar la apertura de ${ejercicio}?`
            )
          }
          disabled={ocupado !== null}
          className="bg-emerald-600 text-white rounded px-4 py-2 disabled:opacity-50"
        >
          {ocupado === "regenerar" ? "Regenerando…" : "Regenerar apertura"}
        </button>
      </div>

      {resultado && (
        <div className="border rounded p-4 mt-6 text-sm bg-green-50">
          <p>
            Asiento de apertura{" "}
            <span className="font-mono">nº {resultado.numero_asiento}</span>{" "}
            (ejercicio {resultado.ejercicio})
          </p>
          <p>
            {resultado.total_lineas} líneas · Debe total{" "}
            {resultado.importe_total_debe}
          </p>
          <p className="font-mono">id: {resultado.asiento_id}</p>
          {resultado.regenerada && (
            <p className="text-emerald-700">Apertura regenerada.</p>
          )}
        </div>
      )}
    </main>
  );
}