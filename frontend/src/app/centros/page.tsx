"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  arbolCentros,
  inactivarCentro,
  reactivarCentro,
  type CentroNodo,
} from "../../components/costcenters/api";
import { ApiError } from "../../components/treasury/api";

const TIPOS: Record<string, string> = {
  departamento: "Departamento",
  proyecto: "Proyecto",
  subvencion: "Subvención",
  delegacion: "Delegación",
};

function NodoArbol({
  nodo,
  onInactivar,
  onReactivar,
}: {
  nodo: CentroNodo;
  onInactivar: (nodo: CentroNodo) => void;
  onReactivar: (nodo: CentroNodo) => void;
}) {
  const esInactivo = nodo.estado === "inactivo";
  return (
    <li className="ml-4">
      <div className="flex items-center gap-2 rounded px-2 py-1 hover:bg-gray-100">
        <span className="text-gray-400">{"–".repeat(nodo.profundidad)}</span>
        <span className="font-mono text-sm">{nodo.codigo}</span>
        <span className="font-medium">{nodo.nombre}</span>
        <span className="text-xs text-gray-500">
          {TIPOS[nodo.tipo] ?? nodo.tipo}
        </span>
        {nodo.n_hijos > 0 && (
          <span className="text-xs text-gray-400">{nodo.n_hijos} hijos</span>
        )}
        {esInactivo && (
          <span className="text-xs bg-amber-100 text-amber-800 rounded px-1">
            inactivo
          </span>
        )}
        <Link
          href={`/centros/nuevo?parent=${nodo.id}`}
          className="text-xs text-blue-600 hover:underline"
        >
          + hijo
        </Link>
        <Link
          href={`/centros/nuevo?editar=${nodo.id}`}
          className="text-xs text-gray-600 hover:underline"
        >
          editar
        </Link>
        {esInactivo ? (
          <button
            type="button"
            onClick={() => onReactivar(nodo)}
            className="text-xs text-emerald-700 hover:underline"
          >
            reactivar
          </button>
        ) : (
          <button
            type="button"
            onClick={() => onInactivar(nodo)}
            className="text-xs text-red-600 hover:underline"
          >
            inactivar
          </button>
        )}
      </div>
      {nodo.hijos?.length > 0 && (
        <ul>
          {nodo.hijos.map((hijo) => (
            <NodoArbol
              key={hijo.id}
              nodo={hijo}
              onInactivar={onInactivar}
              onReactivar={onReactivar}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

export default function CentrosPage() {
  const [raices, setRaices] = useState<CentroNodo[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function recargar() {
    setCargando(true);
    try {
      setRaices(await arbolCentros());
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    } finally {
      setCargando(false);
    }
  }

  useEffect(() => {
    void recargar();
  }, []);

  async function confirmarInactivar(nodo: CentroNodo) {
    const ok = window.confirm(
      `¿Inactivar el centro "${nodo.codigo} · ${nodo.nombre}"?\n` +
        "No se podrá imputar a centros inactivos."
    );
    if (!ok) return;
    setError(null);
    try {
      await inactivarCentro(nodo.id);
      await recargar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    }
  }

  async function reactivar(nodo: CentroNodo) {
    setError(null);
    try {
      await reactivarCentro(nodo.id);
      await recargar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    }
  }

  return (
    <main className="p-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">Centros de coste</h1>
        <Link
          href="/centros/nuevo"
          className="bg-blue-600 text-white rounded px-3 py-1"
        >
          Nuevo centro
        </Link>
      </div>
      {error && <p className="text-red-600 mb-4">{error}</p>}
      {cargando && <p className="text-gray-500 mb-4">Cargando…</p>}
      {!cargando && raices.length === 0 && (
        <p className="text-gray-500">Sin centros de coste todavía.</p>
      )}
      <ul>
        {raices.map((nodo) => (
          <NodoArbol
            key={nodo.id}
            nodo={nodo}
            onInactivar={confirmarInactivar}
            onReactivar={reactivar}
          />
        ))}
      </ul>
    </main>
  );
}