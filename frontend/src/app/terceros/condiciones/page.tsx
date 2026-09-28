import { getToken } from "@/services/client";
import { cabecerasEmpresa } from "@/components/treasury/empresa";
"use client";

import { useCallback, useState } from "react";
import { ApiError } from "../../../components/treasury/api";

interface Condicion {
  id: string;
  empresa_id: number;
  tercero_id: string;
  plazo_dias: number;
  porcentaje: string;
  vigente: boolean;
  override_factura_id: string | null;
}

export default function CondicionesPage() {
  const [terceroId, setTerceroId] = useState("");
  const [condiciones, setCondiciones] = useState<Condicion[]>([]);
  const [plazoDias, setPlazoDias] = useState("10");
  const [porcentaje, setPorcentaje] = useState("2.00");
  const [vigente, setVigente] = useState(true);
  const [overrideFactura, setOverrideFactura] = useState("");
  const [aviso, setAviso] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);

  const cargar = useCallback(async (tercero: string) => {
    setCargando(true);
    setAviso(null);
    try {
      const respuesta = await fetch(`/api/v1/terceros/${tercero}/condiciones`, { headers: { ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() } });
      if (!respuesta.ok) {
        throw new ApiError(respuesta.status, "No se pudieron cargar condiciones");
      }
      setCondiciones((await respuesta.json()) as Condicion[]);
    } catch (error) {
      if (error instanceof ApiError) setAviso(error.message);
      setCondiciones([]);
    } finally {
      setCargando(false);
    }
  }, []);

  function buscar() {
    if (terceroId.trim()) void cargar(terceroId.trim());
  }

  async function guardar() {
    setAviso(null);
    const body = {
      plazo_dias: Number(plazoDias),
      porcentaje: porcentaje || "0.00",
      vigente,
      override_factura_id: overrideFactura || null,
    };
    try {
      const respuesta = await fetch(
        `/api/v1/terceros/${terceroId.trim()}/condiciones`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
          body: JSON.stringify(body),
        }
      );
      if (!respuesta.ok) {
        const detalle = (await respuesta.json()) as { detail?: string };
        throw new ApiError(respuesta.status, detalle.detail ?? "Error");
      }
      await cargar(terceroId.trim());
      setAviso("Condición guardada");
    } catch (error) {
      if (error instanceof ApiError) setAviso(error.message);
    }
  }

  async function desactivar(condicion: Condicion) {
    setAviso(null);
    try {
      const respuesta = await fetch(
        `/api/v1/terceros/condiciones/${condicion.id}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json", ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}), ...cabecerasEmpresa() },
          body: JSON.stringify({ vigente: false }),
        }
      );
      if (!respuesta.ok) {
        throw new ApiError(respuesta.status, "No se pudo desactivar");
      }
      await cargar(terceroId.trim());
    } catch (error) {
      if (error instanceof ApiError) setAviso(error.message);
    }
  }

  return (
    <main className="p-6 max-w-4xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">
        Condiciones de pronto pago
      </h1>

      <section className="border rounded p-4 mb-4">
        <div className="flex gap-3 items-end">
          <label className="block">
            Tercero (id)
            <input
              className="w-80 border rounded p-1"
              value={terceroId}
              onChange={(e) => setTerceroId(e.target.value)}
            />
          </label>
          <button
            className="bg-slate-800 text-white rounded px-3 py-1"
            onClick={buscar}
            disabled={cargando}
          >
            {cargando ? "Cargando…" : "Cargar condiciones"}
          </button>
        </div>
        {aviso && <p className="mt-2 text-sm text-amber-700">{aviso}</p>}
      </section>

      <section className="border rounded p-4 mb-4">
        <h2 className="font-medium mb-2">Nueva condición</h2>
        <div className="grid grid-cols-4 gap-3 mb-3">
          <label className="block">
            Plazo (días)
            <input
              className="w-full border rounded p-1"
              type="number"
              min={1}
              value={plazoDias}
              onChange={(e) => setPlazoDias(e.target.value)}
            />
          </label>
          <label className="block">
            % descuento
            <input
              className="w-full border rounded p-1"
              type="number"
              min={0}
              max={100}
              step="0.01"
              value={porcentaje}
              onChange={(e) => setPorcentaje(e.target.value)}
            />
          </label>
          <label className="block flex items-center gap-2 mt-6">
            <input
              type="checkbox"
              checked={vigente}
              onChange={(e) => setVigente(e.target.checked)}
            />
            Vigente
          </label>
          <label className="block">
            Override factura id
            <input
              className="w-full border rounded p-1"
              value={overrideFactura}
              onChange={(e) => setOverrideFactura(e.target.value)}
            />
          </label>
        </div>
        <button
          className="bg-blue-600 text-white rounded px-4 py-2"
          onClick={guardar}
          disabled={!terceroId.trim()}
        >
          Guardar condición
        </button>
      </section>

      <section className="border rounded overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left border-b">
              <th className="p-2">Plazo</th>
              <th>%</th>
              <th>Vigente</th>
              <th>Override factura</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {condiciones.map((condicion) => (
              <tr key={condicion.id} className="border-b">
                <td className="p-2">{condicion.plazo_dias} días</td>
                <td>{condicion.porcentaje}%</td>
                <td>{condicion.vigente ? "Sí" : "No"}</td>
                <td>{condicion.override_factura_id ?? "—"}</td>
                <td>
                  {condicion.vigente && (
                    <button
                      className="border rounded px-2 py-1 text-xs"
                      onClick={() => void desactivar(condicion)}
                    >
                      Desactivar
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {condiciones.length === 0 && (
              <tr>
                <td className="p-2" colSpan={5}>
                  Sin condiciones para este tercero.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </main>
  );
}