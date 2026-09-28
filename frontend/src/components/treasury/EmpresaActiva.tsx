"use client";

import { useEffect, useState } from "react";

import { getEmpresaActiva, setEmpresaActiva } from "./empresa";

export default function EmpresaActiva() {
  const [valor, setValor] = useState("");
  const [guardado, setGuardado] = useState<string | null>(null);

  useEffect(() => {
    const actual = getEmpresaActiva();
    setGuardado(actual);
    setValor(actual ?? "");
  }, []);

  function aplicar() {
    setEmpresaActiva(valor);
    setGuardado(getEmpresaActiva());
  }

  return (
    <div className="border-b bg-slate-50 px-6 py-2 flex items-center gap-2 text-sm">
      <span className="font-medium">Empresa activa:</span>
      <input
        className="border rounded px-2 py-1 w-40"
        value={valor}
        onChange={(evento) => setValor(evento.target.value)}
        placeholder="empresa_id"
        inputMode="numeric"
      />
      <button
        className="bg-slate-800 text-white rounded px-3 py-1"
        onClick={aplicar}
      >
        Aplicar
      </button>
      <span className={guardado ? "text-emerald-700" : "text-amber-700"}>
        {guardado
          ? `id ${guardado}`
          : "sin definir (las llamadas al API darán 403)"}
      </span>
    </div>
  );
}
