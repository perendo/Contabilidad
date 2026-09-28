"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";

import CuentaPicker from "../../../components/ngo/CuentaPicker";
import {
  ApiError,
  crearCaja,
  formatearImporte,
  listarCajas,
  type Caja,
} from "../../../components/ngo/api";
import type { CuentaSugerida } from "../../../services/acct/api";

export default function CajaPage() {
  const [items, setItems] = useState<Caja[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [mensaje, setMensaje] = useState<string | null>(null);
  const [creando, setCreando] = useState(false);

  const [nombre, setNombre] = useState("");
  const [tipo, setTipo] = useState("caja");
  const [cuenta570, setCuenta570] = useState<CuentaSugerida | null>(null);

  const consultar = useCallback(async () => {
    setError(null);
    try {
      const cuerpo = await listarCajas();
      setItems(cuerpo.items);
      setTotal(cuerpo.total);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    }
  }, []);

  useEffect(() => {
    consultar();
  }, [consultar]);

  async function alCrear(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!cuenta570) {
      setError("Selecciona una subcuenta 570");
      return;
    }
    try {
      await crearCaja({
        nombre,
        cuenta_570_id: Number(cuenta570.id),
        tipo,
      });
      setNombre("");
      setTipo("caja");
      setCuenta570(null);
      setCreando(false);
      setMensaje("Caja creada correctamente");
      consultar();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Error de conexión");
    }
  }

  return (
    <main className="p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">Caja y arqueos</h1>
        <button
          onClick={() => setCreando((v) => !v)}
          className="bg-blue-600 text-white rounded px-4 py-2"
        >
          {creando ? "Cancelar" : "Nueva caja"}
        </button>
      </div>

      {mensaje && <p className="text-green-700 mb-4">{mensaje}</p>}
      {error && <p className="text-red-600 mb-4">{error}</p>}

      {creando && (
        <form
          onSubmit={alCrear}
          className="border rounded p-4 mb-6 bg-gray-50 grid grid-cols-2 gap-3"
        >
          <input
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            placeholder="Nombre (p. ej. Caja principal)"
            required
            className="border rounded px-3 py-2"
          />
          <select
            value={tipo}
            onChange={(e) => setTipo(e.target.value)}
            className="border rounded px-3 py-2"
          >
            <option value="caja">Caja</option>
            <option value="caja_chica">Caja chica</option>
          </select>
          <div className="col-span-2">
            <label className="text-sm text-gray-600 block mb-1">
              Subcuenta 570
            </label>
            <CuentaPicker
              valor=""
              alCambiar={setCuenta570}
              placeholder="Buscar 570…"
            />
          </div>
          <button
            type="submit"
            className="bg-green-600 text-white rounded px-4 py-2 col-span-2"
          >
            Guardar
          </button>
        </form>
      )}

      <p className="text-sm text-gray-600 mb-2">Total: {total}</p>

      <table className="w-full text-sm border rounded">
        <thead>
          <tr className="text-left bg-gray-100">
            <th className="p-2">Nombre</th>
            <th className="p-2">Tipo</th>
            <th className="p-2">Cuenta 570</th>
            <th className="p-2">Estado</th>
            <th className="p-2">Saldo</th>
          </tr>
        </thead>
        <tbody>
          {items.map((c) => (
            <tr key={c.id} className="border-t">
              <td className="p-2">
                <Link
                  className="text-blue-600 underline"
                  href={`/ong/caja/${c.id}`}
                >
                  {c.nombre}
                </Link>
              </td>
              <td className="p-2">{c.tipo}</td>
              <td className="p-2 font-mono">{c.cuenta_570_id}</td>
              <td className="p-2">{c.estado}</td>
              <td className="p-2 font-mono">{formatearImporte(c.saldo)}</td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td colSpan={5} className="p-2 text-gray-500">
                Sin cajas creadas
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </main>
  );
}