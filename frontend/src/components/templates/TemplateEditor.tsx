"use client";

import { useMemo, useRef, useState } from "react";

import { get } from "../../services/client";
import { AccountAutocomplete, type CuentaSugerida } from "../acct/AccountAutocomplete";
import { ApiError } from "../treasury/api";
import { crearPlantilla, type TemplateInput } from "./api";

interface Sugerencias {
  items: CuentaSugerida[];
}

type ModoLinea = "fijo" | "variable";

interface VariableDraft {
  key: string;
  id: string;
  nombre: string;
  esRequerida: boolean;
}

interface LineaDraft {
  key: string;
  cuentaId: string;
  posicion: "debe" | "haber";
  modo: ModoLinea;
  importeFijo: string;
  variableKey: string;
}

interface LineaResuelta {
  debe: number;
  haber: number;
}

function nuevoUuid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return "00000000-0000-4000-8000-" + Math.random().toString(16).slice(2, 14);
}

function clave(): string {
  return Math.random().toString(36).slice(2);
}

function lineaVacia(variableKey = ""): LineaDraft {
  return { key: clave(), cuentaId: "", posicion: "debe", modo: "fijo", importeFijo: "", variableKey };
}

function resolverLineas(lineas: LineaDraft[], variables: Record<string, string>): LineaResuelta[] {
  return lineas
    .map((linea) => {
      const importe = linea.modo === "fijo" ? Number(linea.importeFijo) || 0 : Number(variables[linea.variableKey]) || 0;
      return { debe: linea.posicion === "debe" ? importe : 0, haber: linea.posicion === "haber" ? importe : 0 };
    })
    .filter((linea) => linea.debe > 0 || linea.haber > 0);
}

export default function TemplateEditor({ onCreada }: { onCreada: (id: string) => void }) {
  const [nombre, setNombre] = useState("");
  const [categoria, setCategoria] = useState("");
  const [variables, setVariables] = useState<VariableDraft[]>([]);
  const [lineas, setLineas] = useState<LineaDraft[]>([lineaVacia(), lineaVacia()]);
  const [sugerencias, setSugerencias] = useState<CuentaSugerida[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);
  const seleccionando = useRef(false);

  async function buscar(query: string) {
    if (!query.trim()) {
      setSugerencias([]);
      return;
    }
    try {
      const parametros = new URLSearchParams({ q: query, limit: "20" });
      const cuerpo = await get<Sugerencias>(`/api/v1/accounts/suggest?${parametros}`);
      setSugerencias(cuerpo.items);
    } catch (causa) {
      if (!(causa instanceof ApiError)) throw causa;
      setSugerencias([]);
    }
  }

  function editarLinea(indice: number, parche: Partial<LineaDraft>) {
    setLineas((prev) => prev.map((linea, i) => (i === indice ? { ...linea, ...parche } : linea)));
    setError(null);
  }

  function anadirLinea(indice: number) {
    setLineas((prev) => [...prev.slice(0, indice + 1), lineaVacia(variables[0]?.key ?? ""), ...prev.slice(indice + 1)]);
    setTimeout(() => {
      const contenedor = filasRef.current[indice + 1];
      contenedor?.querySelector<HTMLInputElement>("input")?.focus();
    }, 0);
  }

  function quitarLinea(indice: number) {
    setLineas((prev) => (prev.length > 2 ? prev.filter((_, i) => i !== indice) : prev));
  }

  function anadirVariable() {
    const draft: VariableDraft = { key: clave(), id: nuevoUuid(), nombre: "", esRequerida: true };
    setVariables((prev) => [...prev, draft]);
    setError(null);
  }

  function editarVariable(indice: number, parche: Partial<VariableDraft>) {
    setVariables((prev) => prev.map((variable, i) => (i === indice ? { ...variable, ...parche } : variable)));
  }

  function quitarVariable(indice: number) {
    const variable = variables[indice];
    setVariables((prev) => prev.filter((_, i) => i !== indice));
    setLineas((prev) => prev.map((linea) => (linea.variableKey === variable.key ? { ...linea, variableKey: "", modo: "fijo" } : linea)));
  }

  const filasRef = useRef<Array<HTMLDivElement | null>>([]);
  const totales = useMemo(() => resolverLineas(lineas, {}), [lineas]);

  function manejarTeclado(evento: React.KeyboardEvent<HTMLDivElement>, indice: number) {
    if (evento.key === "Enter" && seleccionando.current) {
      seleccionando.current = false;
      evento.preventDefault();
      return;
    }
    if (evento.key === "Enter") {
      evento.preventDefault();
      anadirLinea(indice);
    }
    if (evento.ctrlKey && (evento.key === "Delete" || evento.key === "Backspace")) {
      evento.preventDefault();
      quitarLinea(indice);
    }
  }

  function construirCuerpo(): TemplateInput {
    const variablesPayload = variables.map((variable) => ({
      id: variable.id,
      nombre: variable.nombre.trim(),
      es_requerida: variable.esRequerida,
    }));
    const porKey = new Map(variables.map((variable) => [variable.key, variable]));
    const lineasPayload = lineas.map((linea, indice) => {
      const base = { orden: indice + 1, cuenta_id: Number(linea.cuentaId), posicion: linea.posicion } as TemplateInput["lineas"][number];
      if (linea.modo === "variable") {
        const variable = porKey.get(linea.variableKey);
        if (variable) base.variable_id = variable.id;
        return base;
      }
      base.importe_fijo = linea.importeFijo;
      return base;
    });
    return {
      nombre: nombre.trim(),
      ...(categoria.trim() ? { categoria: categoria.trim() } : {}),
      variables: variablesPayload,
      lineas: lineasPayload,
    };
  }

  async function guardar() {
    setError(null);
    if (!nombre.trim()) {
      setError("El nombre es obligatorio");
      return;
    }
    if (variables.some((variable) => !variable.nombre.trim())) {
      setError("Toda variable necesita un nombre");
      return;
    }
    if (lineas.some((linea) => !linea.cuentaId)) {
      setError("Toda linea necesita una cuenta");
      return;
    }
    setGuardando(true);
    try {
      const creada = await crearPlantilla(construirCuerpo());
      onCreada(creada.id);
    } catch (causa) {
      setError(causa instanceof Error ? causa.message : "No se pudo crear la plantilla");
    } finally {
      setGuardando(false);
    }
  }

  const sumaFijos = totales.reduce((suma, linea) => suma + linea.debe + linea.haber, 0);

  return (
    <div className="flex flex-col gap-5">
      <div className="grid gap-4 md:grid-cols-3">
        <label className="block">
          Nombre
          <input className="mt-1 block w-full rounded border p-2" value={nombre} onChange={(e) => setNombre(e.target.value)} />
        </label>
        <label className="block">
          Categoria
          <input className="mt-1 block w-full rounded border p-2" value={categoria} onChange={(e) => setCategoria(e.target.value)} />
        </label>
      </div>

      <section className="rounded border bg-white p-4">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">Variables</h2>
          <button type="button" className="rounded border px-3 py-1" onClick={anadirVariable}>
            Anadir variable
          </button>
        </div>
        {variables.length === 0 && <p className="mt-2 text-sm text-gray-500">Sin variables: solo importes fijos.</p>}
        <ul className="mt-3 space-y-2">
          {variables.map((variable, indice) => (
            <li key={variable.key} className="flex items-center gap-3">
              <input
                className="flex-1 rounded border p-2"
                placeholder="Nombre de la variable"
                value={variable.nombre}
                onChange={(e) => editarVariable(indice, { nombre: e.target.value })}
              />
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={variable.esRequerida} onChange={(e) => editarVariable(indice, { esRequerida: e.target.checked })} />
                Requerida
              </label>
              <button type="button" className="rounded border px-2 py-1" onClick={() => quitarVariable(indice)}>
                Quitar
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className="rounded border bg-white p-4">
        <h2 className="font-semibold">Lineas</h2>
        <div className="mt-3 flex flex-col gap-3">
          {lineas.map((linea, indice) => (
            <div
              key={linea.key}
              ref={(el) => {
                filasRef.current[indice] = el;
              }}
              className="flex flex-wrap items-end gap-2"
              onKeyDown={(e) => manejarTeclado(e, indice)}
            >
              <div className="min-w-56 flex-1">
                <AccountAutocomplete
                  value={linea.cuentaId}
                  onChange={(cuenta) => {
                    seleccionando.current = Boolean(cuenta);
                    editarLinea(indice, { cuentaId: cuenta ? String(cuenta.id) : "" });
                  }}
                  onSearch={buscar}
                  sugerencias={sugerencias}
                  placeholder="Cuenta (codigo)..."
                />
              </div>
              <label className="flex flex-col gap-1 text-sm">
                Posicion
                <select className="rounded border p-2" value={linea.posicion} onChange={(e) => editarLinea(indice, { posicion: e.target.value as "debe" | "haber" })}>
                  <option value="debe">Debe</option>
                  <option value="haber">Haber</option>
                </select>
              </label>
              <label className="flex flex-col gap-1 text-sm">
                Tipo
                <select className="rounded border p-2" value={linea.modo} onChange={(e) => editarLinea(indice, { modo: e.target.value as ModoLinea })}>
                  <option value="fijo">Importe fijo</option>
                  <option value="variable">Variable</option>
                </select>
              </label>
              {linea.modo === "fijo" ? (
                <label className="flex flex-col gap-1 text-sm">
                  Importe
                  <input className="w-32 rounded border p-2 font-mono" inputMode="decimal" value={linea.importeFijo} onChange={(e) => editarLinea(indice, { importeFijo: e.target.value })} />
                </label>
              ) : (
                <label className="flex flex-col gap-1 text-sm">
                  Variable
                  <select className="rounded border p-2" value={linea.variableKey} onChange={(e) => editarLinea(indice, { variableKey: e.target.value })}>
                    <option value="">Selecciona...</option>
                    {variables.map((variable) => (
                      <option key={variable.key} value={variable.key}>{variable.nombre || "(sin nombre)"}</option>
                    ))}
                  </select>
                </label>
              )}
              <button type="button" className="rounded border px-2 py-1" aria-label={`Quitar linea ${indice + 1}`} onClick={() => quitarLinea(indice)}>
                X
              </button>
            </div>
          ))}
        </div>
        <div className="mt-3 flex items-center gap-3 text-sm text-gray-600">
          <button type="button" className="rounded border px-3 py-1" onClick={() => anadirLinea(lineas.length - 1)}>
            Anadir linea (Enter)
          </button>
          <span>Suma de importes fijos: {sumaFijos.toFixed(4)}</span>
        </div>
      </section>

      {error && <p className="text-red-600">{error}</p>}
      <div>
        <button type="button" disabled={guardando} className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50" onClick={() => void guardar()}>
          {guardando ? "Guardando..." : "Guardar plantilla"}
        </button>
      </div>
    </div>
  );
}
