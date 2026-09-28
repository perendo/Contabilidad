"use client";

import { useCallback, useEffect, useState } from "react";

import { sugerirCuentas, type CuentaSugerida } from "../../services/acct/api";

export default function CuentaPicker({
  valor,
  alCambiar,
  placeholder = "Buscar cuenta…",
}: {
  valor: string;
  alCambiar: (cuenta: CuentaSugerida) => void;
  placeholder?: string;
}) {
  const [consulta, setConsulta] = useState(valor);
  const [sugerencias, setSugerencias] = useState<CuentaSugerida[]>([]);
  const [abierto, setAbierto] = useState(false);

  useEffect(() => {
    setConsulta(valor);
  }, [valor]);

  const buscar = useCallback(async (q: string) => {
    if (!q.trim()) {
      setSugerencias([]);
      return;
    }
    try {
      const cuerpo = await sugerirCuentas(q, 10);
      setSugerencias(cuerpo.items);
      setAbierto(true);
    } catch {
      setSugerencias([]);
    }
  }, []);

  return (
    <div className="relative">
      <input
        value={consulta}
        onChange={(e) => {
          setConsulta(e.target.value);
          buscar(e.target.value);
        }}
        onBlur={() => setTimeout(() => setAbierto(false), 150)}
        placeholder={placeholder}
        className="border rounded px-3 py-2 w-full"
      />
      {abierto && sugerencias.length > 0 && (
        <ul className="absolute z-10 bg-white border rounded mt-1 w-full max-h-48 overflow-auto">
          {sugerencias.map((s) => (
            <li key={s.code}>
              <button
                type="button"
                onMouseDown={() => {
                  setConsulta(`${s.code} · ${s.name}`);
                  setAbierto(false);
                  alCambiar(s);
                }}
                className="w-full text-left px-3 py-1 hover:bg-gray-100 text-sm"
              >
                <span className="font-mono">{s.code}</span> · {s.name}
              </button>
            </li>
          ))}
        </ul>
      )}
      {!abierto && consulta && !valor && (
        <p className="text-xs text-gray-500 mt-1">
          {sugerencias.length === 0 ? "Sin coincidencias" : ""}
        </p>
      )}
    </div>
  );
}