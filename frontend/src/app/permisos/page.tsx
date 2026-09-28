"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  conceder,
  obtenerCatalogo,
  obtenerMatriz,
  obtenerMisPermisos,
  puedeConfigurar,
  resetMatriz,
  revocar,
  type CatalogoModulo,
  type MatrizItem,
  type MisPermisos,
} from "../../components/rbac/api";
import PermisosTable from "../../components/rbac/permisos-table";

export default function PermisosPage() {
  const [roles, setRoles] = useState<string[]>([]);
  const [catalogo, setCatalogo] = useState<CatalogoModulo[]>([]);
  const [items, setItems] = useState<MatrizItem[]>([]);
  const [mis, setMis] = useState<MisPermisos | null>(null);
  const [error, setError] = useState<string | null>(null);

  const consultar = useCallback(async () => {
    setError(null);
    try {
      const [cat, matriz, propios] = await Promise.all([
        obtenerCatalogo(),
        obtenerMatriz(),
        obtenerMisPermisos(),
      ]);
      setCatalogo(cat.modulos);
      setRoles(matriz.roles);
      setItems(matriz.items);
      setMis(propios);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    }
  }, []);

  useEffect(() => {
    consultar();
  }, [consultar]);

  const alternar = useCallback(
    async (rolId: string, modulo: string, operacion: string, concedido: boolean) => {
      setError(null);
      try {
        if (concedido) {
          await conceder(rolId, modulo, operacion);
        } else {
          const actual = items.find(
            (i) => i.rol_id === rolId && i.modulo === modulo && i.operacion === operacion
          );
          if (!actual) return;
          await revocar(actual.matriz_id);
        }
        await consultar();
      } catch (e) {
        if (e instanceof ApiError) setError(e.message);
        else setError("Error de conexión");
      }
    },
    [items, consultar]
  );

  const reiniciar = useCallback(async () => {
    setError(null);
    try {
      await resetMatriz();
      await consultar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    }
  }, [consultar]);

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">Permisos por rol</h1>
        <div className="flex items-center gap-4">
          {mis?.rol && <span className="text-sm text-gray-600">Rol: {mis.rol}</span>}
          <Link className="text-blue-600 underline text-sm" href="/permisos/auditoria">
            Auditoría de accesos
          </Link>
        </div>
      </div>

      {error && <p className="text-red-600 mb-4">{error}</p>}

      <PermisosTable
        roles={roles}
        catalogo={catalogo}
        items={items}
        puedeEditar={puedeConfigurar(mis)}
        onToggle={alternar}
        onReset={reiniciar}
      />
    </main>
  );
}
