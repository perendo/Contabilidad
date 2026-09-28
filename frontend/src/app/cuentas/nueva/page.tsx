"use client";

import { useEffect, useRef, useState } from "react";
import { crearCuenta, sugerirCuentas, type CuentaSugerida } from "@/services/acct/api";
import { AccountAutocomplete } from "@/components/acct/AccountAutocomplete";

export interface CuentaFormData {
  code: string;
  name: string;
  parent_id: string | null;
}

export default function NuevaCuentaPage() {
  const [formData, setFormData] = useState<CuentaFormData>({
    code: "",
    name: "",
    parent_id: null,
  });
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState(false);
  const [sugerenciasPadre, setSugerenciasPadre] = useState<CuentaSugerida[]>([]);
  const debouncePadre = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (debouncePadre.current) clearTimeout(debouncePadre.current);
    };
  }, []);

  const handleCodeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({ ...formData, code: e.target.value });
  };

  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({ ...formData, name: e.target.value });
  };

  const handlePadreSeleccionado = (cuenta: CuentaSugerida | null) => {
    setFormData({ ...formData, parent_id: cuenta?.id || null });
    setSugerenciasPadre([]);
  };

  const handleBuscarPadre = (query: string) => {
    if (debouncePadre.current) clearTimeout(debouncePadre.current);
    if (query.length < 1) {
      setSugerenciasPadre([]);
      return;
    }
    debouncePadre.current = setTimeout(async () => {
      try {
        const data = await sugerirCuentas(query, 20);
        // Filtrar solo cuentas que NO son hojas (nivel < 4) para poder ser padres
        setSugerenciasPadre(data.items.filter(c => c.level < 4));
      } catch {
        setSugerenciasPadre([]);
      }
    }, 250);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setExito(false);
    setCargando(true);

    try {
      await crearCuenta({
        code: formData.code,
        name: formData.name,
        parent_id: formData.parent_id || undefined,
      });
      setExito(true);
      setFormData({ code: "", name: "", parent_id: null });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al crear la cuenta");
    } finally {
      setCargando(false);
    }
  };

  // Calcular nivel esperado basado en el código
  const nivelEsperado = formData.code.length <= 4 ? formData.code.length : 
                       (formData.code.length >= 5 && formData.code.length <= 8 ? 5 : 0);

  return (
    <div className="p-4 max-w-2xl">
      <h1 className="text-2xl font-bold mb-4">Nueva Cuenta / Subcuenta</h1>

      {exito && (
        <div className="mb-4 p-3 bg-green-100 text-green-800 rounded">
          Cuenta creada correctamente
        </div>
      )}

      {error && (
        <div className="mb-4 p-3 bg-red-100 text-red-800 rounded">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4 bg-white p-6 rounded-lg shadow border">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Código *
          </label>
          <input
            type="text"
            value={formData.code}
            onChange={handleCodeChange}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="Ej: 43000001"
            maxLength={8}
            required
            pattern="[0-9]+"
            disabled={cargando}
          />
          <p className="mt-1 text-sm text-gray-500">
            Solo dígitos. Nivel 1-4: longitud = nivel. Nivel 5: 5-8 dígitos.
            {nivelEsperado > 0 && <span className="ml-2">Nivel estimado: {nivelEsperado}</span>}
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Nombre *
          </label>
          <input
            type="text"
            value={formData.name}
            onChange={handleNameChange}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="Ej: Cliente Acme S.L."
            maxLength={200}
            required
            disabled={cargando}
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Cuenta Padre (opcional)
          </label>
          <AccountAutocomplete
            value={formData.parent_id ? `${formData.parent_id}` : ""}
            onChange={handlePadreSeleccionado}
            onSearch={handleBuscarPadre}
            sugerencias={sugerenciasPadre}
            placeholder="Buscar cuenta padre (solo niveles 1-3)..."
            disabled={cargando}
          />
          <p className="mt-1 text-sm text-gray-500">
            Solo cuentas de nivel 1-3 (grupos, subgrupos, cuentas). Las subcuentas (nivel 4) no pueden tener hijas.
            {formData.parent_id && <span className="text-blue-600 ml-2">Padre seleccionado</span>}
          </p>
        </div>

        <div className="pt-4 border-t">
          <button
            type="submit"
            disabled={cargando}
            className="w-full py-2 px-4 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {cargando ? "Creando..." : "Crear Cuenta"}
          </button>
        </div>
      </form>

      <div className="mt-6 p-4 bg-gray-50 rounded-lg">
        <h3 className="font-medium mb-2">Reglas del Plan de Cuentas</h3>
        <ul className="text-sm text-gray-600 space-y-1">
          <li>• Código único por empresa (máx. 8 dígitos)</li>
          <li>• Nivel = longitud del código (1-4 dígitos) o nivel 5 (5-8 dígitos)</li>
          <li>• Profundidad máxima: 5 niveles</li>
          <li>• Solo hojas nivel ≥ 4 son apuntables (is_selectable)</li>
          <li>• Al crear una hija, la madre deja de ser apuntable</li>
          <li>• Cuentas con asientos no se pueden desactivar</li>
        </ul>
      </div>
    </div>
  );
}