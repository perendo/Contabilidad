"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import {
  crearCentro,
  editarCentro,
  obtenerCentro,
  type CentroCoste,
} from "../../../components/costcenters/api";
import CentroSelect from "../../../components/costcenters/CentroSelect";
import { ApiError } from "../../../components/treasury/api";

const TIPOS = [
  ["departamento", "Departamento"],
  ["proyecto", "Proyecto"],
  ["subvencion", "Subvención"],
  ["delegacion", "Delegación"],
] as const;

function Formulario() {
  const router = useRouter();
  const params = useSearchParams();
  const parentIni = params.get("parent");
  const editarId = params.get("editar");

  const [codigo, setCodigo] = useState("");
  const [nombre, setNombre] = useState("");
  const [tipo, setTipo] = useState("departamento");
  const [parentId, setParentId] = useState(parentIni ?? "");
  const [subvencionId, setSubvencionId] = useState("");
  const [esEdicion, setEsEdicion] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    if (!editarId) {
      setEsEdicion(false);
      return;
    }
    setEsEdicion(true);
    obtenerCentro(editarId)
      .then((centro: CentroCoste) => {
        setCodigo(centro.codigo);
        setNombre(centro.nombre);
        setTipo(centro.tipo);
        setParentId(centro.parent_id ?? "");
      })
      .catch((e: unknown) => {
        if (e instanceof ApiError) setError(e.message);
        else setError("Error de conexión");
      });
  }, [editarId]);

  async function guardar(f?: FocusEvent) {
    f?.preventDefault();
    setError(null);
    setGuardando(true);
    const body: Record<string, unknown> = {
      codigo,
      nombre,
      tipo,
      parent_id: parentId || null,
      subvencion_id: subvencionId || null,
    };
    try {
      if (esEdicion && editarId) {
        await editarCentro(editarId, {
          nombre,
          tipo,
          parent_id: parentId || null,
          subvencion_id: subvencionId || null,
        });
      } else {
        await crearCentro(body);
      }
      router.push("/centros");
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
      setGuardando(false);
    }
  }

  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        await guardar(undefined);
      }}
      className="flex flex-col gap-4 max-w-xl"
    >
      {error && <p className="text-red-600">{error}</p>}
      <label className="flex flex-col gap-1">
        Código
        <input
          value={codigo}
          disabled={esEdicion}
          onChange={(e) => setCodigo(e.target.value)}
          className="border rounded px-3 py-1 font-mono"
          maxLength={20}
          required
        />
      </label>
      <label className="flex flex-col gap-1">
        Nombre
        <input
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          className="border rounded px-3 py-1"
          maxLength={120}
          required
        />
      </label>
      <label className="flex flex-col gap-1">
        Tipo
        <select
          value={tipo}
          onChange={(e) => setTipo(e.target.value)}
          className="border rounded px-3 py-1"
        >
          {TIPOS.map(([valor, etiqueta]) => (
            <option key={valor} value={valor}>
              {etiqueta}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        Centro padre (opcional)
        <CentroSelect
          value={parentId}
          onChange={setParentId}
          soloActivos={false}
        />
      </label>
      <label className="flex flex-col gap-1">
        Subvención (opcional)
        <input
          value={subvencionId}
          onChange={(e) => setSubvencionId(e.target.value)}
          className="border rounded px-3 py-1 font-mono"
          placeholder="uuid de la subvención"
        />
      </label>
      <div className="flex gap-3">
        <button
          type="submit"
          disabled={guardando}
          className="bg-blue-600 text-white rounded px-4 py-1 disabled:opacity-50"
        >
          {esEdicion ? "Guardar cambios" : "Crear centro"}
        </button>
        <button
          type="button"
          onClick={() => router.push("/centros")}
          className="border rounded px-4 py-1"
        >
          Cancelar
        </button>
      </div>
    </form>
  );
}

export default function NuevoCentroPage() {
  return (
    <main className="p-6 max-w-6xl mx-auto">
      <h1 className="text-xl font-semibold mb-6">
        <Suspense fallback={null}>
          <Titulo />
        </Suspense>
      </h1>
      <Suspense fallback={null}>
        <Formulario />
      </Suspense>
    </main>
  );
}

function Titulo() {
  const params = useSearchParams();
  return params.get("editar") ? "Editar centro de coste" : "Nuevo centro de coste";
}