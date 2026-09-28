"use client";

import { useState, useCallback, useEffect, KeyboardEvent } from "react";

export interface CuentaNodo {
  id: string;
  code: string;
  name: string;
  level: number;
  is_selectable: boolean;
  is_active: boolean;
  parent_id: string | null;
  children: CuentaNodo[];
}

interface CuentaNodoProps {
  nodo: CuentaNodo;
  nivel: number;
  onToggle: (id: string) => void;
  abiertos: Set<string>;
}

function CuentaNodoItem({ nodo, nivel, onToggle, abiertos }: CuentaNodoProps) {
  const tieneHijos = nodo.children.length > 0;
  const estaAbierto = abiertos.has(nodo.id);
  const esHoja = !tieneHijos;
  const esApuntable = nodo.is_selectable && nodo.is_active;
  const inactiva = !nodo.is_active;

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Enter" || e.key === " ") {
      if (tieneHijos) {
        e.preventDefault();
        onToggle(nodo.id);
      }
    } else if (e.key === "ArrowRight" && tieneHijos && !estaAbierto) {
      e.preventDefault();
      onToggle(nodo.id);
    } else if (e.key === "ArrowLeft" && tieneHijos && estaAbierto) {
      e.preventDefault();
      onToggle(nodo.id);
    }
  };

  return (
    <div>
      <div
        className={`flex items-center gap-2 px-2 py-1 rounded ${
          inactiva ? "text-gray-400" : "text-gray-900"
        } ${nivel > 0 ? "pl-4" : ""}`}
        onKeyDown={handleKeyDown}
        onClick={() => tieneHijos && onToggle(nodo.id)}
        role="treeitem"
        aria-expanded={tieneHijos ? estaAbierto : undefined}
        aria-selected={false}
        aria-level={nivel + 1}
        tabIndex={0}
        style={{ userSelect: "none" }}
      >
        {tieneHijos && (
          <span
            className={`inline-flex items-center justify-center w-5 h-5 text-gray-500 ${
              estaAbierto ? "rotate-90" : ""
            }`}
            aria-hidden="true"
          >
            ▶
          </span>
        )}
        {!tieneHijos && <span className="w-5" aria-hidden="true" />}

        <span className="font-mono text-sm font-medium text-blue-700 min-w-[4rem]">
          {nodo.code}
        </span>
        <span className="flex-1 text-sm">{nodo.name}</span>

        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs ${
              esApuntable
                ? "bg-green-100 text-green-700"
                : inactiva
                ? "bg-gray-100 text-gray-500"
                : "bg-yellow-100 text-yellow-700"
            }`}
          >
            {esApuntable ? "Apuntable" : inactiva ? "Inactiva" : "No apuntable"}
          </span>
          {esHoja && esApuntable && (
            <span className="text-xs text-green-600" title="Cuenta apuntable (hoja nivel ≥ 4)">
              ✓
            </span>
          )}
          {inactiva && (
            <span className="text-xs text-gray-400" title="Cuenta inactiva">
              ⏸
            </span>
          )}
        </div>
      </div>

      {tieneHijos && estaAbierto && (
        <div className="border-l-2 border-gray-200 ml-5 pl-2">
          {nodo.children.map((hijo) => (
            <CuentaNodoItem
              key={hijo.id}
              nodo={hijo}
              nivel={nivel + 1}
              onToggle={onToggle}
              abiertos={abiertos}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function PlanTree({ nodos }: { nodos: CuentaNodo[] }) {
  const [abiertos, setAbiertos] = useState<Set<string>>(new Set());

  const toggle = useCallback((id: string) => {
    setAbiertos((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  // Expandir primer nivel por defecto (en efecto, no durante el render)
  useEffect(() => {
    setAbiertos(new Set(nodos.map((n) => n.id)));
  }, [nodos]);

  if (nodos.length === 0) {
    return (
      <div className="p-8 text-center text-gray-500">
        <p className="text-lg">No hay cuentas en el plan de cuentas</p>
        <p className="text-sm mt-1">Cree una nueva cuenta para comenzar</p>
      </div>
    );
  }

  return (
    <div className="overflow-auto max-h-[70vh]" role="tree" aria-label="Plan de cuentas">
      {nodos.map((nodo) => (
        <CuentaNodoItem
          key={nodo.id}
          nodo={nodo}
          nivel={0}
          onToggle={toggle}
          abiertos={abiertos}
        />
      ))}
    </div>
  );
}