"use client";

import { useMemo } from "react";

import type { CatalogoModulo, MatrizItem } from "./api";

interface Props {
  roles: string[];
  catalogo: CatalogoModulo[];
  items: MatrizItem[];
  puedeEditar: boolean;
  onToggle: (
    rolId: string,
    modulo: string,
    operacion: string,
    concedido: boolean
  ) => void;
  onReset: () => void;
}

export default function PermisosTable({
  roles,
  catalogo,
  items,
  puedeEditar,
  onToggle,
  onReset,
}: Props) {
  const concesiones = useMemo(() => {
    const mapa = new Map<string, string>();
    items.forEach((i) => mapa.set(`${i.rol_id}|${i.modulo}|${i.operacion}`, i.matriz_id));
    return mapa;
  }, [items]);

  const rolIds = useMemo(() => {
    const mapa = new Map<string, string>();
    items.forEach((i) => {
      if (!mapa.has(i.rol)) mapa.set(i.rol, i.rol_id);
    });
    return mapa;
  }, [items]);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Matriz de permisos</h2>
        <button
          type="button"
          onClick={onReset}
          disabled={!puedeEditar}
          className="border rounded px-3 py-1 disabled:opacity-50"
        >
          Restablecer al seed
        </button>
      </div>

      <table className="w-full text-sm border rounded">
        <thead>
          <tr className="text-left bg-gray-100">
            <th className="p-2">Módulo</th>
            <th className="p-2">Operación</th>
            {roles.map((rol) => (
              <th key={rol} className="p-2">
                {rol}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {catalogo.map((modulo) =>
            modulo.operaciones.map((operacion, indice) => (
              <tr key={`${modulo.modulo}-${operacion}`} className="border-t">
                {indice === 0 && (
                  <td rowSpan={modulo.operaciones.length} className="p-2 align-top font-mono">
                    {modulo.modulo}
                  </td>
                )}
                <td className="p-2">{operacion}</td>
                {roles.map((rol) => {
                  const rolId = rolIds.get(rol);
                  const clave = rolId ? `${rolId}|${modulo.modulo}|${operacion}` : "";
                  const concedido = clave !== "" && concesiones.has(clave);
                  return (
                    <td key={rol} className="p-2">
                      <input
                        type="checkbox"
                        checked={concedido}
                        disabled={!puedeEditar || !rolId}
                        onChange={() =>
                          rolId && onToggle(rolId, modulo.modulo, operacion, !concedido)
                        }
                      />
                    </td>
                  );
                })}
              </tr>
            ))
          )}
        </tbody>
      </table>

      {!puedeEditar && (
        <p className="text-sm text-gray-600 mt-2">
          Solo el rol con <code>rbac/configurar</code> puede modificar la matriz.
        </p>
      )}
    </div>
  );
}
