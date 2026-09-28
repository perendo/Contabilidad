"use client";

import { useState } from "react";
import {
  actualizarCuenta,
  ApiError,
  type ActualizarCuentaResponse,
} from "@/services/acct/api";

export interface CuentaEditable {
  id: string;
  code: string;
  name: string;
  level?: number;
  is_selectable?: boolean;
  is_active: boolean;
}

interface AccountEditProps {
  cuenta: CuentaEditable;
  onGuardado?: (cuenta: ActualizarCuentaResponse) => void;
  onCancelar?: () => void;
}

export function AccountEdit({ cuenta, onGuardado, onCancelar }: AccountEditProps) {
  const [nombre, setNombre] = useState(cuenta.name);
  const [activa, setActiva] = useState(cuenta.is_active);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState(false);

  const sinCambios = nombre.trim() === cuenta.name && activa === cuenta.is_active;
  const desactiva = cuenta.is_active && !activa;
  const esApuntable = (cuenta.is_selectable ?? false) && cuenta.is_active;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setExito(false);
    if (sinCambios) {
      setError("Sin cambios que guardar");
      return;
    }
    if (nombre.trim().length < 1) {
      setError("El nombre es obligatorio");
      return;
    }
    setCargando(true);
    try {
      const actualizada = await actualizarCuenta(cuenta.id, {
        name: nombre.trim() !== cuenta.name ? nombre.trim() : undefined,
        is_active: activa !== cuenta.is_active ? activa : undefined,
      });
      setExito(true);
      onGuardado?.(actualizada);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError(
          `${err.message}. La cuenta puede tener asientos asociados (protegida) o el nombre ya existe en la empresa.`
        );
      } else if (err instanceof ApiError && err.status === 404) {
        setError("La cuenta no existe en la empresa activa.");
      } else {
        setError(err instanceof Error ? err.message : "Error al guardar los cambios");
      }
    } finally {
      setCargando(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-4 bg-white p-6 rounded-lg shadow border"
      aria-label={`Editar cuenta ${cuenta.code}`}
    >
      <div className="flex items-center gap-2">
        <span className="font-mono text-sm font-medium text-blue-700">{cuenta.code}</span>
        <span
          className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs ${
            esApuntable
              ? "bg-green-100 text-green-700"
              : !cuenta.is_active
                ? "bg-gray-100 text-gray-500"
                : "bg-yellow-100 text-yellow-700"
          }`}
        >
          {esApuntable ? "Apuntable" : !cuenta.is_active ? "Inactiva" : "No apuntable"}
        </span>
      </div>

      <div>
        <label
          htmlFor={`account-name-${cuenta.id}`}
          className="block text-sm font-medium text-gray-700 mb-1"
        >
          Nombre *
        </label>
        <input
          id={`account-name-${cuenta.id}`}
          type="text"
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          maxLength={200}
          required
          disabled={cargando}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
        />
      </div>

      <div className="flex items-center gap-2">
        <input
          id={`account-active-${cuenta.id}`}
          type="checkbox"
          checked={activa}
          onChange={(e) => setActiva(e.target.checked)}
          disabled={cargando}
          className="h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
        />
        <label htmlFor={`account-active-${cuenta.id}`} className="text-sm text-gray-700">
          Cuenta activa
        </label>
      </div>

      <div
        className="p-3 rounded-md bg-amber-50 border border-amber-200 text-sm text-amber-800"
        role="note"
      >
        Protección: si la cuenta tiene asientos asociados o hijas, la desactivación será
        rechazada (409) y el estado quedará intacto. Renombrar a un nombre ya usado en la
        empresa también devuelve 409.
        {desactiva && (
          <p className="mt-1 font-medium">
            Vas a desactivar esta cuenta. Si tiene imputaciones, el servidor lo bloqueará.
          </p>
        )}
      </div>

      {exito && (
        <div className="p-3 bg-green-100 text-green-800 rounded text-sm" role="status">
          Cambios guardados correctamente
        </div>
      )}

      {error && (
        <div className="p-3 bg-red-100 text-red-800 rounded text-sm" role="alert">
          {error}
        </div>
      )}

      <div className="flex gap-2 pt-2">
        <button
          type="submit"
          disabled={cargando || sinCambios}
          className="flex-1 py-2 px-4 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {cargando ? "Guardando..." : "Guardar cambios"}
        </button>
        {onCancelar && (
          <button
            type="button"
            onClick={onCancelar}
            disabled={cargando}
            className="py-2 px-4 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
          >
            Cancelar
          </button>
        )}
      </div>
    </form>
  );
}
