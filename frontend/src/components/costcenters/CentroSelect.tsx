"use client";

import { useEffect, useMemo, useState } from "react";

import {
  aplanarArbol,
  arbolCentros,
  type CentroCoste,
} from "./api";

interface Props {
  value: string;
  onChange: (centroId: string) => void;
  soloHojas?: boolean;
  soloActivos?: boolean;
  placeholder?: string;
  className?: string;
}

/** Select de centros del árbol de la empresa activa (autocarga). */
export default function CentroSelect({
  value,
  onChange,
  soloHojas = false,
  soloActivos = true,
  placeholder = "Centro de coste…",
  className = "border rounded px-2 py-1 w-60",
}: Props) {
  const [centros, setCentros] = useState<CentroCoste[]>([]);

  useEffect(() => {
    arbolCentros()
      .then((nodos) => setCentros(aplanarArbol(nodos)))
      .catch(() => setCentros([]));
  }, []);

  const opciones = useMemo(
    () =>
      centros.filter(
        (c) =>
          (!soloActivos || c.estado === "activo") &&
          (!soloHojas || c.es_hoja)
      ),
    [centros, soloActivos, soloHojas]
  );

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={className}
    >
      <option value="">— {placeholder} —</option>
      {opciones.map((c) => (
        <option key={c.id} value={c.id}>
          {c.codigo} · {c.nombre}
        </option>
      ))}
    </select>
  );
}