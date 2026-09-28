"use client";

import { useState, useRef, useEffect, useCallback } from "react";

export interface CuentaSugerida {
  id: string;
  code: string;
  name: string;
  level: number;
  is_selectable: boolean;
  is_active: boolean;
  tenant_id: number;
}

interface AccountAutocompleteProps {
  value: string;
  onChange: (cuenta: CuentaSugerida | null) => void;
  onSearch: (query: string) => void;
  sugerencias: CuentaSugerida[];
  placeholder?: string;
  disabled?: boolean;
}

export function AccountAutocomplete({
  value,
  onChange,
  onSearch,
  sugerencias,
  placeholder = "Buscar cuenta...",
  disabled = false,
}: AccountAutocompleteProps) {
  const [query, setQuery] = useState("");
  const [abierto, setAbierto] = useState(false);
  const [indiceSeleccionado, setIndiceSeleccionado] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const listaRef = useRef<HTMLUListElement>(null);

  // Actualizar query cuando cambia value (cuando se selecciona una cuenta)
  useEffect(() => {
    if (value) {
      // Buscar la cuenta en sugerencias para mostrar su código
      const cuenta = sugerencias.find(c => c.id === value);
      if (cuenta) {
        setQuery(`${cuenta.code} - ${cuenta.name}`);
      }
    }
  }, [value, sugerencias]);

  // Manejar teclado
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (!abierto || sugerencias.length === 0) return;

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setIndiceSeleccionado(prev => Math.min(prev + 1, sugerencias.length - 1));
        break;
      case "ArrowUp":
        e.preventDefault();
        setIndiceSeleccionado(prev => Math.max(prev - 1, 0));
        break;
      case "Enter":
        e.preventDefault();
        if (indiceSeleccionado >= 0 && sugerencias[indiceSeleccionado]) {
          onChange(sugerencias[indiceSeleccionado]);
          setAbierto(false);
          setIndiceSeleccionado(-1);
        }
        break;
      case "Tab":
        if (indiceSeleccionado >= 0 && sugerencias[indiceSeleccionado]) {
          e.preventDefault();
          onChange(sugerencias[indiceSeleccionado]);
          setAbierto(false);
          setIndiceSeleccionado(-1);
        }
        break;
      case "Escape":
        setAbierto(false);
        setIndiceSeleccionado(-1);
        break;
    }
  }, [abierto, sugerencias, indiceSeleccionado, onChange]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newQuery = e.target.value;
    setQuery(newQuery);
    setAbierto(true);
    setIndiceSeleccionado(-1);
    onSearch(newQuery);
  };

  const handleClickOutside = useCallback((e: MouseEvent) => {
    if (inputRef.current && !inputRef.current.contains(e.target as Node)) {
      if (listaRef.current && !listaRef.current.contains(e.target as Node)) {
        setAbierto(false);
        setIndiceSeleccionado(-1);
      }
    }
  }, []);

  useEffect(() => {
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [handleClickOutside]);

  const handleItemClick = (cuenta: CuentaSugerida) => {
    onChange(cuenta);
    setAbierto(false);
    setIndiceSeleccionado(-1);
  };

  const handleBlur = () => {
    // Delay para permitir click en sugerencia
    setTimeout(() => {
      setAbierto(false);
      setIndiceSeleccionado(-1);
    }, 200);
  };

  return (
    <div className="relative" ref={inputRef}>
      <input
        type="text"
        value={query}
        onChange={handleInputChange}
        onKeyDown={handleKeyDown}
        onFocus={() => {
          if (query.length >= 1) setAbierto(true);
        }}
        onBlur={handleBlur}
        placeholder={placeholder}
        disabled={disabled}
        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
        autoComplete="off"
      />

      {abierto && sugerencias.length > 0 && (
        <ul
          ref={listaRef}
          className="absolute z-10 w-full mt-1 bg-white border border-gray-300 rounded-md shadow-lg max-h-60 overflow-auto"
          role="listbox"
        >
          {sugerencias.map((cuenta, index) => (
            <li
              key={cuenta.id}
              className={`px-3 py-2 cursor-pointer ${
                index === indiceSeleccionado ? "bg-blue-100" : "hover:bg-gray-100"
              }`}
              role="option"
              aria-selected={index === indiceSeleccionado}
              onClick={() => handleItemClick(cuenta)}
            >
              <div className="flex items-center gap-2">
                <span className="font-mono text-sm text-blue-700 font-medium">
                  {cuenta.code}
                </span>
                <span className="text-sm text-gray-900">{cuenta.name}</span>
                <span className="text-xs text-gray-500">
                  Nivel {cuenta.level}
                  {cuenta.is_selectable && " · Apuntable"}
                  {!cuenta.is_active && " · Inactiva"}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}

      {abierto && sugerencias.length === 0 && query.length >= 1 && (
        <div className="absolute z-10 w-full mt-1 bg-white border border-gray-300 rounded-md shadow-lg p-3 text-gray-500 text-sm">
          No se encontraron cuentas apuntables
        </div>
      )}
    </div>
  );
}