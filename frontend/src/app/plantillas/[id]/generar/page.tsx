"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { generarDesdePlantilla, obtenerPlantilla, type AccountingTemplate } from "../../../../components/templates/api";

interface LineaResuelta {
  orden: number;
  cuentaId: number;
  posicion: "debe" | "haber";
  importe: number;
}

export default function GenerarPlantillaPage() {
  const params = useParams<{ id: string }>();
  const [plantilla, setPlantilla] = useState<AccountingTemplate | null>(null);
  const [fecha, setFecha] = useState(new Date().toISOString().slice(0, 10));
  const [variables, setVariables] = useState<Record<string, string>>({});
  const [mensaje, setMensaje] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmando, setConfirmando] = useState(false);
  const [generando, setGenerando] = useState(false);

  useEffect(() => {
    void obtenerPlantilla(params.id)
      .then(setPlantilla)
      .catch((causa) => setError(causa instanceof Error ? causa.message : "No se pudo cargar"));
  }, [params.id]);

  useEffect(() => {
    function atajo(evento: KeyboardEvent) {
      if (evento.ctrlKey && evento.key === "Enter") {
        evento.preventDefault();
        setConfirmando(true);
      }
    }
    document.addEventListener("keydown", atajo);
    return () => document.removeEventListener("keydown", atajo);
  }, []);

  const resueltas = useMemo<LineaResuelta[]>(() => {
    if (!plantilla) return [];
    return plantilla.lineas
      .map((linea) => {
        const importe = linea.importe_fijo !== null ? Number(linea.importe_fijo) : Number(variables[linea.variable_id ?? ""]) || 0;
        return { orden: linea.orden, cuentaId: linea.cuenta_id, posicion: linea.posicion, importe };
      })
      .filter((linea) => linea.importe > 0);
  }, [plantilla, variables]);

  const totalDebe = resueltas.filter((linea) => linea.posicion === "debe").reduce((suma, linea) => suma + linea.importe, 0);
  const totalHaber = resueltas.filter((linea) => linea.posicion === "haber").reduce((suma, linea) => suma + linea.importe, 0);
  const cuadra = resueltas.length >= 2 && totalDebe > 0 && Math.abs(totalDebe - totalHaber) < 0.0001;
  const faltanRequeridas = (plantilla?.variables ?? []).filter((variable) => variable.es_requerida && !(Number(variables[variable.id]) > 0));

  async function generar() {
    setGenerando(true);
    setError(null);
    setMensaje(null);
    try {
      const resultado = await generarDesdePlantilla(params.id, { fecha_asiento: fecha, variables });
      const asiento = (resultado as { asiento?: { numero_asiento?: number } }).asiento;
      setMensaje(`Asiento ${asiento?.numero_asiento ?? ""} generado correctamente.`);
      setConfirmando(false);
    } catch (causa) {
      setError(causa instanceof Error ? causa.message : "No se pudo generar");
    } finally {
      setGenerando(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl p-6">
      <Link className="text-sm text-blue-700 hover:underline" href={`/plantillas/${params.id}`}>Volver a la plantilla</Link>
      <h1 className="mt-4 text-2xl font-semibold">Generar asiento</h1>
      {plantilla && (
        <div className="mt-6 space-y-5 rounded border bg-white p-6">
          <label className="block">
            Fecha
            <input className="mt-1 block rounded border p-2" type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} />
          </label>

          {plantilla.variables.map((variable) => (
            <label className="block" key={variable.id}>
              {variable.nombre}{variable.es_requerida ? " *" : ""}
              <input
                className="mt-1 block w-full rounded border p-2 font-mono"
                inputMode="decimal"
                value={variables[variable.id] ?? ""}
                onChange={(e) => setVariables((actual) => ({ ...actual, [variable.id]: e.target.value }))}
              />
            </label>
          ))}

          <section className="rounded border p-4">
            <h2 className="font-semibold">Vista previa</h2>
            <ul className="mt-2 space-y-1 text-sm">
              {resueltas.map((linea) => (
                <li key={`${linea.orden}-${linea.cuentaId}`} className="flex justify-between border-b py-1">
                  <span>Cuenta {linea.cuentaId} · {linea.posicion}</span>
                  <span className="font-mono">{linea.importe.toFixed(4)}</span>
                </li>
              ))}
            </ul>
            <p className={cuadra ? "mt-3 text-emerald-700" : "mt-3 text-amber-700"}>
              Debe {totalDebe.toFixed(4)} · Haber {totalHaber.toFixed(4)} · {cuadra ? "Cuadra" : "No cuadra"}
            </p>
          </section>

          {error && <p className="text-red-600">{error}</p>}
          {mensaje && <p className="text-emerald-700">{mensaje}</p>}

          {confirmando ? (
            <div className="flex items-center gap-3">
              <button type="button" disabled={generando} className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50" onClick={() => void generar()}>
                {generando ? "Generando..." : "Confirmar y generar"}
              </button>
              <button type="button" className="rounded border px-4 py-2" onClick={() => setConfirmando(false)}>
                Cancelar
              </button>
            </div>
          ) : (
            <button
              type="button"
              disabled={!cuadra || faltanRequeridas.length > 0}
              className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
              onClick={() => setConfirmando(true)}
            >
              Revisar y generar (Ctrl+Enter)
            </button>
          )}
          {faltanRequeridas.length > 0 && (
            <p className="text-sm text-amber-700">Faltan variables requeridas: {faltanRequeridas.map((variable) => variable.nombre).join(", ")}</p>
          )}
        </div>
      )}
    </main>
  );
}
