"use client";

import { useParams } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";

import {
  ApiError,
  cambiarEstadoSubvencion,
  desimputarGasto,
  exportarInforme,
  formatearImporte,
  imputarGasto,
  listarAsientos,
  obtenerAsiento,
  obtenerInforme,
  obtenerSubvencion,
  type Asiento,
  type GastoInforme,
  type InformeJustificacion,
  type LineaAsiento,
  type Subvencion,
  type SubvencionEstado,
} from "../../../../components/ngo/api";

const TRANSICIONES: Partial<Record<SubvencionEstado, SubvencionEstado[]>> = {
  concedida: ["en_curso"],
  en_curso: ["justificada"],
  justificada: ["reintegrada"],
};

export default function SubvencionDetallePage() {
  const params = useParams<{ id: string }>();
  const id = params.id;

  const [sub, setSub] = useState<Subvencion | null>(null);
  const [informe, setInforme] = useState<InformeJustificacion | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mensaje, setMensaje] = useState<string | null>(null);

  const [asientos, setAsientos] = useState<Asiento[]>([]);
  const [desplegado, setDesplegado] = useState<string | null>(null);
  const [lineas, setLineas] = useState<LineaAsiento[]>([]);
  const [importeLinea, setImporteLinea] = useState("");
  const [partida, setPartida] = useState("");
  const [rectificativo, setRectificativo] = useState("");

  const cargar = useCallback(async () => {
    setError(null);
    try {
      const [s, inf] = await Promise.all([obtenerSubvencion(id), obtenerInforme(id)]);
      setSub(s);
      setInforme(inf);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    }
  }, [id]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  async function cargarAsientos() {
    try {
      const cuerpo = await listarAsientos();
      setAsientos(cuerpo.items);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }

  useEffect(() => {
    cargarAsientos();
  }, []);

  async function desplegarAsiento(asientoId: string) {
    if (desplegado === asientoId) {
      setDesplegado(null);
      setLineas([]);
      return;
    }
    try {
      const detalle = await obtenerAsiento(asientoId);
      setAsientos((prev) => prev.map((a) => (a.id === asientoId ? { ...detalle } : a)));
      setDesplegado(asientoId);
      setLineas(detalle.lineas ?? []);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }

  async function alImputar(
    e: FormEvent,
    asientoId: string,
    linea: LineaAsiento
  ) {
    e.preventDefault();
    setError(null);
    try {
      await imputarGasto(id, {
        asiento_id: asientoId,
        linea_id: linea.id,
        importe_asignado: importeLinea || "0",
        partida: partida || null,
      });
      setImporteLinea("");
      setPartida("");
      setMensaje("Gasto imputado correctamente");
      cargar();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Error de conexión");
    }
  }

  async function alDesimputar(gastoId: string) {
    setError(null);
    try {
      await desimputarGasto(id, gastoId);
      setMensaje("Imputación eliminada");
      cargar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }

  async function cambiarEstado(estado: SubvencionEstado) {
    setError(null);
    try {
      const rectificativoId = estado === "reintegrada" && rectificativo ? rectificativo : null;
      await cambiarEstadoSubvencion(id, estado, rectificativoId);
      setMensaje(`Subvención marcada como ${estado}`);
      cargar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }

  async function exportar(formato: "csv" | "json") {
    setError(null);
    try {
      await exportarInforme(id, formato);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }

  if (!sub || !informe) {
    return (
      <main className="p-6 max-w-5xl mx-auto">
        <h1 className="text-xl font-semibold mb-4">Subvención</h1>
        {error && <p className="text-red-600">{error}</p>}
        <p className="text-gray-500">Cargando…</p>
      </main>
    );
  }

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <h1 className="text-xl font-semibold mb-1">{sub.programa}</h1>
      <p className="text-gray-600 mb-4 text-sm">
        {sub.entidad_concedente} · Ejercicio {sub.ejercicio} · {sub.estado}
      </p>

      {mensaje && <p className="text-green-700 mb-4">{mensaje}</p>}
      {error && <p className="text-red-600 mb-4">{error}</p>}

      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="border rounded p-3">
          <p className="text-sm text-gray-600">Concedido</p>
          <p className="font-mono">{formatearImporte(sub.importe_concedido)}</p>
        </div>
        <div className="border rounded p-3">
          <p className="text-sm text-gray-600">Gastado</p>
          <p className="font-mono">{formatearImporte(sub.gastado)}</p>
        </div>
        <div className="border rounded p-3">
          <p className="text-sm text-gray-600">Pendiente</p>
          <p className="font-mono">{formatearImporte(sub.pendiente)}</p>
        </div>
      </div>

      {sub.partidas && sub.partidas.length > 0 && (
        <p className="text-sm text-gray-600 mb-4">
          Partidas: {sub.partidas.join(", ")}
        </p>
      )}

      <div className="flex items-center gap-3 mb-6">
        {(TRANSICIONES[sub.estado] ?? []).map((destino) => (
          <div key={destino} className="flex items-center gap-2">
            {destino === "reintegrada" && (
              <input
                value={rectificativo}
                onChange={(e) => setRectificativo(e.target.value)}
                placeholder="Asiento rectificativo (UUID)"
                className="border rounded px-3 py-1 text-sm"
              />
            )}
            <button
              onClick={() => cambiarEstado(destino)}
              className="bg-blue-600 text-white rounded px-3 py-1 text-sm"
            >
              Marcar {destino}
            </button>
          </div>
        ))}
        <button
          onClick={() => exportar("csv")}
          className="text-blue-600 underline text-sm"
        >
          Exportar CSV
        </button>
        <button
          onClick={() => exportar("json")}
          className="text-blue-600 underline text-sm"
        >
          Exportar JSON
        </button>
        <span className="text-xs text-gray-500 font-mono ml-auto">
          {informe.huella.slice(0, 16)}…
        </span>
      </div>

      <h2 className="text-lg font-semibold mb-2">Gastos imputados</h2>
      <table className="w-full text-sm border rounded mb-6">
        <thead>
          <tr className="text-left bg-gray-100">
            <th className="p-2">Nº asiento</th>
            <th className="p-2">Fecha</th>
            <th className="p-2">Cuenta</th>
            <th className="p-2">Partida</th>
            <th className="p-2">Importe</th>
            <th className="p-2"></th>
          </tr>
        </thead>
        <tbody>
          {informe.detalle.map((g: GastoInforme) => (
            <tr key={g.id} className="border-t">
              <td className="p-2 font-mono">{g.numero_asiento}</td>
              <td className="p-2">{g.fecha}</td>
              <td className="p-2 font-mono">{g.cuenta}</td>
              <td className="p-2">{g.partida ?? "-"}</td>
              <td className="p-2 font-mono">{formatearImporte(g.importe)}</td>
              <td className="p-2">
                <button
                  onClick={() => alDesimputar(g.id)}
                  className="text-red-600 underline text-xs"
                >
                  Desimputar
                </button>
              </td>
            </tr>
          ))}
          {informe.detalle.length === 0 && (
            <tr>
              <td colSpan={6} className="p-2 text-gray-500">
                Ningún gasto imputado
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <h2 className="text-lg font-semibold mb-2">Imputar gasto del diario</h2>
      <div className="space-y-2">
        {asientos.map((a) => (
          <div key={a.id} className="border rounded p-2">
            <button
              onClick={() => desplegarAsiento(a.id)}
              className="flex items-center gap-3 w-full text-left"
            >
              <span className="font-mono">#{a.numero_asiento}</span>
              <span>{a.fecha}</span>
              <span className="text-gray-600 flex-1">{a.concepto}</span>
              <span className="text-gray-500">{a.estado}</span>
            </button>
            {desplegado === a.id && (
              <table className="w-full text-sm mt-2 border-t">
                <thead>
                  <tr className="text-left">
                    <th className="p-2">Cuenta</th>
                    <th className="p-2">Debe</th>
                    <th className="p-2">Haber</th>
                    <th className="p-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {lineas.map((l) => (
                    <tr key={l.id} className="border-t">
                      <td className="p-2 font-mono">{l.cuenta}</td>
                      <td className="p-2 font-mono">{l.debe}</td>
                      <td className="p-2 font-mono">{l.haber}</td>
                      <td className="p-2">
                        <form
                          onSubmit={(e) => alImputar(e, a.id, l)}
                          className="flex items-center gap-2"
                        >
                          <input
                            value={importeLinea}
                            onChange={(e) => setImporteLinea(e.target.value)}
                            placeholder="Importe"
                            type="number"
                            step="0.0001"
                            className="border rounded px-2 py-1 w-28 text-sm"
                          />
                          <input
                            value={partida}
                            onChange={(e) => setPartida(e.target.value)}
                            placeholder="Partida (opcional)"
                            className="border rounded px-2 py-1 w-36 text-sm"
                          />
                          <button
                            type="submit"
                            className="bg-green-600 text-white rounded px-2 py-1 text-sm"
                          >
                            Imputar
                          </button>
                        </form>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        ))}
        {asientos.length === 0 && (
          <p className="text-gray-500 text-sm">No hay asientos disponibles</p>
        )}
      </div>
    </main>
  );
}