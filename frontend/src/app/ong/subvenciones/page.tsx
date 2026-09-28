"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";

import {
  ApiError,
  crearSubvencion,
  formatearImporte,
  listarSubvenciones,
  type Subvencion,
  type SubvencionEstado,
} from "../../../components/ngo/api";

export default function SubvencionesPage() {
  const [items, setItems] = useState<Subvencion[]>([]);
  const [total, setTotal] = useState(0);
  const [estado, setEstado] = useState<"" | SubvencionEstado>("");
  const [error, setError] = useState<string | null>(null);
  const [creando, setCreando] = useState(false);
  const [mensaje, setMensaje] = useState<string | null>(null);

  const [entidad, setEntidad] = useState("");
  const [programa, setPrograma] = useState("");
  const [referencia, setReferencia] = useState("");
  const [importe, setImporte] = useState("");
  const [ejercicio, setEjercicio] = useState(new Date().getFullYear());
  const [partidas, setPartidas] = useState("");

  const consultar = useCallback(async () => {
    setError(null);
    try {
      const cuerpo = await listarSubvenciones({ estado: estado || undefined });
      setItems(cuerpo.items);
      setTotal(cuerpo.total);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    }
  }, [estado]);

  useEffect(() => {
    consultar();
  }, [consultar]);

  async function alCrear(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setMensaje(null);
    try {
      await crearSubvencion({
        entidad_concedente: entidad,
        programa,
        referencia: referencia || null,
        importe_concedido: importe,
        ejercicio,
        partidas: partidas.trim() ? partidas.split(",").map((p) => p.trim()) : null,
      });
      setEntidad("");
      setPrograma("");
      setReferencia("");
      setImporte("");
      setPartidas("");
      setCreando(false);
      setMensaje("Subvención creada correctamente");
      consultar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    }
  }

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">Subvenciones</h1>
        <div className="flex items-center gap-3">
          <Link href="/ong/libros" className="text-blue-600 underline text-sm">
            Libros y legalización
          </Link>
          <Link href="/ong/caja" className="text-blue-600 underline text-sm">
            Caja y arqueos
          </Link>
          <button
            onClick={() => setCreando((v) => !v)}
            className="bg-blue-600 text-white rounded px-4 py-2"
          >
            {creando ? "Cancelar" : "Nueva subvención"}
          </button>
        </div>
      </div>

      {mensaje && <p className="text-green-700 mb-4">{mensaje}</p>}
      {error && <p className="text-red-600 mb-4">{error}</p>}

      {creando && (
        <form
          onSubmit={alCrear}
          className="border rounded p-4 mb-6 bg-gray-50 grid grid-cols-2 gap-3"
        >
          <input
            value={entidad}
            onChange={(e) => setEntidad(e.target.value)}
            placeholder="Entidad concedente"
            required
            className="border rounded px-3 py-2"
          />
          <input
            value={programa}
            onChange={(e) => setPrograma(e.target.value)}
            placeholder="Programa"
            required
            className="border rounded px-3 py-2"
          />
          <input
            value={referencia}
            onChange={(e) => setReferencia(e.target.value)}
            placeholder="Referencia (opcional)"
            className="border rounded px-3 py-2"
          />
          <input
            value={importe}
            onChange={(e) => setImporte(e.target.value)}
            placeholder="Importe concedido"
            type="number"
            step="0.0001"
            min="0"
            required
            className="border rounded px-3 py-2"
          />
          <input
            value={ejercicio}
            onChange={(e) => setEjercicio(Number(e.target.value))}
            type="number"
            placeholder="Ejercicio"
            required
            className="border rounded px-3 py-2"
          />
          <input
            value={partidas}
            onChange={(e) => setPartidas(e.target.value)}
            placeholder="Partidas (coma separada, opcional)"
            className="border rounded px-3 py-2"
          />
          <button
            type="submit"
            className="bg-green-600 text-white rounded px-4 py-2 col-span-2"
          >
            Guardar
          </button>
        </form>
      )}

      <div className="flex items-center gap-3 mb-4">
        <select
          value={estado}
          onChange={(e) => setEstado(e.target.value as SubvencionEstado)}
          className="border rounded px-3 py-1"
        >
          <option value="">Todos los estados</option>
          <option value="concedida">Concedida</option>
          <option value="en_curso">En curso</option>
          <option value="justificada">Justificada</option>
          <option value="reintegrada">Reintegrada</option>
        </select>
        <p className="text-sm text-gray-600">Total: {total}</p>
      </div>

      <table className="w-full text-sm border rounded">
        <thead>
          <tr className="text-left bg-gray-100">
            <th className="p-2">Referencia</th>
            <th className="p-2">Programa</th>
            <th className="p-2">Entidad</th>
            <th className="p-2">Ejercicio</th>
            <th className="p-2">Concedido</th>
            <th className="p-2">Pendiente</th>
            <th className="p-2">Estado</th>
          </tr>
        </thead>
        <tbody>
          {items.map((s) => (
            <tr key={s.id} className="border-t">
              <td className="p-2">
                <Link
                  className="text-blue-600 underline font-mono"
                  href={`/ong/subvenciones/${s.id}`}
                >
                  {s.referencia ?? s.programa}
                </Link>
              </td>
              <td className="p-2">{s.programa}</td>
              <td className="p-2">{s.entidad_concedente}</td>
              <td className="p-2">{s.ejercicio}</td>
              <td className="p-2 font-mono">{formatearImporte(s.importe_concedido)}</td>
              <td className="p-2 font-mono">{formatearImporte(s.pendiente)}</td>
              <td className="p-2">{s.estado}</td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td colSpan={7} className="p-2 text-gray-500">
                Sin subvenciones registradas
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </main>
  );
}