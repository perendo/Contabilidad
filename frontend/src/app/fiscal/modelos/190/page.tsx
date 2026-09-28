"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import {
  ApiError,
  descargarModelo190,
  generarModelo190,
  listarModelos190,
  validarModelo190,
  type Modelo190,
  type ValidacionNif190,
} from "@/components/fiscal/api";
import { suscribirEmpresa } from "@/components/treasury/empresa";

const TAMANO_PAGINA = 50;

export default function Modelo190Page() {
  const [items, setItems] = useState<Modelo190[]>([]);
  const [total, setTotal] = useState(0);
  const [ejercicio, setEjercicio] = useState(new Date().getFullYear());
  const [offset, setOffset] = useState(0);
  const [validacion, setValidacion] = useState<ValidacionNif190 | null>(null);
  const [cargando, setCargando] = useState(true);
  const [validando, setValidando] = useState(false);
  const [generando, setGenerando] = useState(false);
  const [descargandoId, setDescargandoId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mensaje, setMensaje] = useState<string | null>(null);
  const [revisionEmpresa, setRevisionEmpresa] = useState(0);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const respuesta = await listarModelos190({
        ejercicio: ejercicio || undefined,
        limit: TAMANO_PAGINA,
        offset,
      });
      setItems(respuesta.items);
      setTotal(respuesta.total);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error al listar los modelos 190");
    } finally {
      setCargando(false);
    }
  }, [ejercicio, offset]);

  useEffect(() => {
    void cargar();
  }, [cargar, revisionEmpresa]);

  useEffect(() => {
    return suscribirEmpresa(() => {
      setOffset(0);
      setValidacion(null);
      setRevisionEmpresa((revision) => revision + 1);
    });
  }, []);

  async function validar() {
    if (!Number.isInteger(ejercicio)) return;
    setValidando(true);
    setError(null);
    setMensaje(null);
    try {
      const resultado = await validarModelo190(ejercicio);
      setValidacion(resultado);
      if (resultado.valido) {
        setError(null);
        setMensaje("Todos los perceptores tienen NIF.");
      } else {
        setError("Hay perceptores sin NIF. Deben completarse antes de generar el modelo 190.");
        setMensaje(null);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error al validar los NIF");
    } finally {
      setValidando(false);
    }
  }

  async function generar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    if (!Number.isInteger(ejercicio)) return;
    if (validacion && !validacion.valido) {
      setError("No se puede generar el modelo 190 porque hay perceptores sin NIF.");
      return;
    }
    setGenerando(true);
    setError(null);
    setMensaje(null);
    try {
      const modelo = await generarModelo190({ ejercicio });
      await cargar();
      setMensaje(`Modelo 190 generado con identificador ${modelo.id}.`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error al generar el modelo 190");
    } finally {
      setGenerando(false);
    }
  }

  async function descargar(modelo: Modelo190) {
    setDescargandoId(modelo.id);
    setError(null);
    setMensaje(null);
    try {
      await descargarModelo190(
        modelo.id,
        modelo.nombre_fichero ?? `modelo-190-${modelo.id}.csv`
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error al descargar el modelo 190");
    } finally {
      setDescargandoId(null);
    }
  }

  return (
    <main className="mx-auto max-w-6xl space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="text-xs text-gray-500">
            <Link href="/fiscal/retenciones" className="hover:underline">
              Retenciones IRPF
            </Link>{" "}
            / Modelo 190
          </div>
          <h1 className="mt-1 text-2xl font-bold">Modelo 190</h1>
          <p className="text-sm text-gray-500">
            Declaración anual de retenciones e ingresos a cuenta por perceptor
          </p>
        </div>
        <Link
          href="/fiscal/retenciones"
          className="rounded border px-4 py-2 text-sm font-semibold text-blue-700 hover:bg-blue-50"
        >
          Ver liquidaciones
        </Link>
      </div>

      {error && (
        <div className="rounded border border-red-200 bg-red-50 p-4 text-red-700">
          {error}
        </div>
      )}
      {mensaje && (
        <div className="rounded border border-green-200 bg-green-50 p-4 text-green-700">
          {mensaje}
        </div>
      )}

      <section className="rounded border bg-white p-6">
        <h2 className="text-lg font-semibold">Validación y generación</h2>
        <p className="mt-1 text-sm text-gray-500">
          Todos los perceptores con retenciones del ejercicio deben tener NIF configurado.
        </p>
        <form onSubmit={generar} className="mt-4 flex flex-wrap items-end gap-3">
          <label className="block text-sm font-semibold text-gray-600">
            Ejercicio
            <input
              type="number"
              min="1900"
              max="9999"
              required
              value={ejercicio}
              onChange={(e) => {
                setEjercicio(e.currentTarget.valueAsNumber);
                setOffset(0);
                setValidacion(null);
              }}
              className="mt-1 block w-32 rounded border p-2"
            />
          </label>
          <button
            type="button"
            onClick={() => void validar()}
            disabled={validando || generando || !Number.isInteger(ejercicio)}
            className="rounded border border-blue-600 px-4 py-2 text-sm font-semibold text-blue-700 hover:bg-blue-50 disabled:opacity-50"
          >
            {validando ? "Validando…" : "Validar NIF"}
          </button>
          <button
            type="submit"
            disabled={generando || validando || !Number.isInteger(ejercicio)}
            className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {generando ? "Generando…" : "Generar modelo 190"}
          </button>
        </form>

        {validacion && validacion.valido && (
          <div className="mt-4 rounded border border-green-200 bg-green-50 p-3 text-sm text-green-800">
            Validación correcta: todos los perceptores tienen NIF.
          </div>
        )}
        {validacion && !validacion.valido && (
          <div className="mt-4 rounded border border-red-200 bg-red-50 p-4 text-sm text-red-800">
            <p className="font-semibold">Perceptores sin NIF:</p>
            <ul className="mt-2 list-inside list-disc space-y-1">
              {(validacion.perceptores_sin_nif ?? []).map((perceptor) => (
                <li key={perceptor.tercero_id}>
                  {perceptor.nombre} ({perceptor.tercero_id})
                </li>
              ))}
            </ul>
            {(validacion.perceptores_sin_nif ?? []).length === 0 && (
              <p className="mt-2">El backend no identificó los perceptores.</p>
            )}
          </div>
        )}
      </section>

      <div className="overflow-x-auto rounded border bg-white">
        <table className="w-full min-w-[800px] text-sm">
          <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-3">Ejercicio</th>
              <th className="px-4 py-3">Perceptores</th>
              <th className="px-4 py-3">Generado</th>
              <th className="px-4 py-3">SHA-256</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {items.map((modelo) => (
              <tr key={modelo.id} className="border-t hover:bg-gray-50">
                <td className="px-4 py-3 font-semibold">{modelo.ejercicio}</td>
                <td className="px-4 py-3">{modelo.n_perceptores}</td>
                <td className="px-4 py-3">{modelo.fecha_generacion}</td>
                <td className="max-w-xs truncate px-4 py-3 font-mono text-xs">
                  {modelo.hash_contenido}
                </td>
                <td className="px-4 py-3 text-right">
                  <button
                    type="button"
                    onClick={() => void descargar(modelo)}
                    disabled={descargandoId !== null}
                    className="text-blue-700 underline disabled:opacity-40"
                  >
                    {descargandoId === modelo.id ? "Descargando…" : "Descargar"}
                  </button>
                </td>
              </tr>
            ))}
            {!cargando && items.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                  No hay modelos 190 generados para este ejercicio.
                </td>
              </tr>
            )}
            {cargando && items.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gray-500">
                  Cargando modelos 190…
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-sm text-gray-500">
        <span>
          {total === 0 ? 0 : offset + 1}–{offset + items.length} de {total}
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={offset === 0 || cargando}
            onClick={() => setOffset(Math.max(0, offset - TAMANO_PAGINA))}
            className="rounded border px-3 py-1.5 disabled:opacity-40"
          >
            Anterior
          </button>
          <button
            type="button"
            disabled={cargando || offset + items.length >= total}
            onClick={() => setOffset(offset + TAMANO_PAGINA)}
            className="rounded border px-3 py-1.5 disabled:opacity-40"
          >
            Siguiente
          </button>
        </div>
      </div>
    </main>
  );
}
