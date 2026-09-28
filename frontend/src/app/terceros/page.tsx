"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../../components/treasury/api";
import { get } from "../../services/client";

interface Tercero {
  id: string;
  nif: string | null;
  razon_social: string;
  es_cliente: boolean;
  es_proveedor: boolean;
  activo: boolean;
}

export default function TercerosPage() {
  const [items, setItems] = useState<Tercero[]>([]);
  const [total, setTotal] = useState(0);
  const [rol, setRol] = useState("");
  const [q, setQ] = useState("");
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setError(null);
    try {
      const params = new URLSearchParams();
      if (rol) params.set("rol", rol);
      if (q) params.set("q", q);
      const cuerpo = await get<{ total: number; items: Tercero[] }>(
        `/api/v1/terceros?${params}`
      );
      setItems(cuerpo.items);
      setTotal(cuerpo.total);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }, [rol, q]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <div className="flex items-baseline justify-between mb-4">
        <h1 className="text-xl font-semibold">Terceros</h1>
        <Link href="/terceros/nuevo" className="bg-blue-600 text-white rounded px-3 py-1">
          Nuevo tercero
        </Link>
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          cargar();
        }}
        className="flex gap-3 mb-4"
      >
        <select value={rol} onChange={(e) => setRol(e.target.value)} className="border rounded px-2 py-1">
          <option value="">Todos</option>
          <option value="cliente">Clientes</option>
          <option value="proveedor">Proveedores</option>
        </select>
        <input
          placeholder="Buscar por razón social"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="border rounded px-3 py-1 flex-1"
        />
        <button type="submit" className="bg-slate-800 text-white rounded px-3 py-1">
          Buscar
        </button>
      </form>
      {error && <p className="text-red-600 mb-4">{error}</p>}
      <p className="mb-2">Total {total}</p>
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b">
            <th className="text-left p-2">NIF</th>
            <th className="text-left p-2">Razón social</th>
            <th className="text-left p-2">Rol</th>
            <th className="text-left p-2">Estado</th>
          </tr>
        </thead>
        <tbody>
          {items.map((t) => (
            <tr key={t.id} className="border-b">
              <td className="p-2 font-mono">{t.nif}</td>
              <td className="p-2">
                <Link href={`/terceros/${t.id}`} className="text-blue-700 underline">
                  {t.razon_social}
                </Link>
              </td>
              <td className="p-2">
                {[t.es_cliente && "Cliente", t.es_proveedor && "Proveedor"]
                  .filter(Boolean)
                  .join(" / ")}
              </td>
              <td className="p-2">{t.activo ? "Activo" : "Inactivo"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
