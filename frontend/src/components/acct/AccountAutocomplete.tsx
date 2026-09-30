"use client";

/**
 * AUTOCOMPLETADO Y CONSULTA DE CUENTAS PGC
 *
 * - Si se teclea el código o nombre, busca y valida la cuenta contable apuntable.
 * - Doble clic abre el desplegable con las cuentas apuntables disponibles del PGC.
 * - Si la cuenta tecleada no existe, muestra enlace directo para darla de alta en /cuentas/nueva.
 * - Soporta navegación por teclado (flechas arriba/abajo, Enter, Esc).
 * - Alto contraste: fondo blanco, texto negro y selección azul con texto blanco.
 */

import { useState, useRef, useEffect, useCallback } from "react";
import Link from "next/link";

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
  placeholder = "Buscar o doble clic para ver PGC...",
  disabled = false,
}: AccountAutocompleteProps) {
  const [query, setQuery] = useState("");
  const [abierto, setAbierto] = useState(false);
  const [indiceSeleccionado, setIndiceSeleccionado] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const listaRef = useRef<HTMLUListElement>(null);

  // Actualizar query cuando cambia value (cuando se selecciona o carga una cuenta)
  useEffect(() => {
    if (value) {
      const cuenta = sugerencias.find((c) => String(c.id) === String(value));
      if (cuenta) {
        setQuery(`${cuenta.code} - ${cuenta.name}`);
      }
    }
  }, [value, sugerencias]);

  // Manejar teclado
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!abierto || sugerencias.length === 0) {
        if (e.key === "ArrowDown" && !abierto) {
          e.preventDefault();
          onSearch(query.trim() || "");
          setAbierto(true);
        }
        return;
      }
      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          setIndiceSeleccionado((prev) => Math.min(prev + 1, sugerencias.length - 1));
          break;
        case "ArrowUp":
          e.preventDefault();
          setIndiceSeleccionado((prev) => Math.max(prev - 1, 0));
          break;
        case "Enter":
        case "Tab":
          if (indiceSeleccionado >= 0 && sugerencias[indiceSeleccionado]) {
            e.preventDefault();
            const elegida = sugerencias[indiceSeleccionado];
            onChange(elegida);
            setQuery(`${elegida.code} - ${elegida.name}`);
            setAbierto(false);
            setIndiceSeleccionado(-1);
          }
          break;
        case "Escape":
          setAbierto(false);
          setIndiceSeleccionado(-1);
          break;
      }
    },
    [abierto, sugerencias, indiceSeleccionado, onChange, onSearch, query]
  );

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newQuery = e.target.value;
    setQuery(newQuery);
    setAbierto(true);
    setIndiceSeleccionado(-1);
    onSearch(newQuery);
  };

  // Doble clic: abre el desplegable para consultar cuentas del PGC
  const handleDoubleClick = () => {
    if (disabled) return;
    onSearch(query.trim());
    setAbierto(true);
    setIndiceSeleccionado(-1);
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
    setQuery(`${cuenta.code} - ${cuenta.name}`);
    setAbierto(false);
    setIndiceSeleccionado(-1);
  };

  // Código limpio de lo que el usuario ha tecleado (solo dígitos iniciales si escribió "4000...")
  const codigoLimpio = query.trim().split(" ")[0].replace(/[^0-9]/g, "");

  return (
    <div className="relative" ref={inputRef}>
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={handleInputChange}
          onDoubleClick={handleDoubleClick}
          onKeyDown={handleKeyDown}
          onFocus={() => {
            if (query.length >= 1) setAbierto(true);
          }}
          placeholder={placeholder}
          disabled={disabled}
          title="Doble clic para consultar el Plan General Contable o escribe para buscar/validar"
          className="w-full px-3 py-2 pr-8 bg-white text-slate-900 border border-slate-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-600 disabled:bg-slate-100 placeholder:text-slate-400 font-medium text-xs sm:text-sm"
          autoComplete="off"
        />
        <button
          type="button"
          tabIndex={-1}
          onClick={() => {
            if (!abierto) {
              onSearch(query.trim());
              setAbierto(true);
            } else {
              setAbierto(false);
            }
          }}
          title="Consultar PGC"
          className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700 p-1"
        >
          <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5">
            <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd" />
          </svg>
        </button>
      </div>

      {abierto && sugerencias.length > 0 && (
        <ul
          ref={listaRef}
          className="absolute z-50 w-full mt-1 bg-white border border-slate-300 rounded-xl shadow-2xl max-h-64 overflow-auto p-1 divide-y divide-slate-100"
          role="listbox"
        >
          <li className="px-3 py-1.5 text-[11px] font-semibold text-slate-500 bg-slate-50 rounded-t-lg flex justify-between items-center">
            <span>Cuentas PGC Disponibles (Apuntables)</span>
            <span className="text-[10px] text-slate-400">{sugerencias.length} resultado(s)</span>
          </li>
          {sugerencias.map((cuenta, index) => {
            const esSeleccionado = index === indiceSeleccionado;
            return (
              <li
                key={cuenta.id}
                className={[
                  "px-3 py-2 cursor-pointer rounded-lg transition-colors text-xs flex items-center justify-between",
                  esSeleccionado
                    ? "bg-blue-600 text-white font-semibold"
                    : "text-slate-900 hover:bg-slate-100",
                ].join(" ")}
                role="option"
                aria-selected={esSeleccionado}
                onClick={() => handleItemClick(cuenta)}
              >
                <div className="flex items-center gap-2 truncate">
                  <span
                    className={[
                      "font-mono font-bold px-1.5 py-0.5 rounded text-xs",
                      esSeleccionado
                        ? "bg-blue-800 text-white"
                        : "bg-slate-100 text-blue-700 border border-slate-200",
                    ].join(" ")}
                  >
                    {cuenta.code}
                  </span>
                  <span className="truncate">{cuenta.name}</span>
                </div>
                <div className="shrink-0 text-[11px] ml-2">
                  <span
                    className={[
                      "font-mono text-[10px]",
                      esSeleccionado ? "text-blue-100" : "text-emerald-700 font-medium",
                    ].join(" ")}
                  >
                    Nivel {cuenta.level} · Apuntable
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {/* Si no existe la cuenta o no se encuentran cuentas con la búsqueda */}
      {abierto && sugerencias.length === 0 && (
        <div
          ref={listaRef as any}
          className="absolute z-50 w-full mt-1 bg-white border border-slate-300 rounded-xl shadow-2xl p-3.5 text-xs text-slate-700 space-y-2"
        >
          <div className="flex items-center gap-1.5 text-amber-700 font-semibold">
            <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 text-amber-600">
              <path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
            </svg>
            <span>Cuenta no encontrada en el PGC</span>
          </div>

          <p className="text-slate-600 text-[11px] leading-relaxed">
            La cuenta <strong className="text-slate-900 font-mono">{query || "(vacía)"}</strong> no existe como cuenta apuntable en la empresa activa.
          </p>

          <div className="pt-2 border-t border-slate-200 flex items-center justify-between">
            <span className="text-[11px] text-slate-500">¿Deseas darla de alta ahora?</span>
            <Link
              href={codigoLimpio ? `/cuentas/nueva?code=${encodeURIComponent(codigoLimpio)}` : "/cuentas/nueva"}
              className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-lg text-xs flex items-center gap-1 transition-colors shadow-sm"
              onClick={() => setAbierto(false)}
            >
              <span>+ Alta en PGC</span>
              <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5">
                <path fillRule="evenodd" d="M3 10a.75.75 0 01.75-.75h10.638L10.23 5.29a.75.75 0 111.04-1.08l5.5 5.25a.75.75 0 010 1.08l-5.5 5.25a.75.75 0 11-1.04-1.08l4.158-3.96H3.75A.75.75 0 013 10z" clipRule="evenodd" />
              </svg>
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
