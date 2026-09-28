"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";

import {
  ApiError,
  darDeBaja,
  editarActivo,
  generarAmortizacion,
  obtenerActivo,
  type Activo,
} from "../../../components/inmovilizado/api";

const ETIQUETA_ESTADO: Record<string, string> = {
  en_uso: "En uso",
  dado_de_baja: "Dado de baja",
};

export default function DetalleActivoPage() {
  const { id } = useParams<{ id: string }>();
  const [activo, setActivo] = useState<Activo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState<string | null>(null);

  const [periodo, setPeriodo] = useState(new Date().getMonth() + 1);
  const [ejercicio, setEjercicio] = useState(new Date().getFullYear());

  const [fechaBaja, setFechaBaja] = useState("");
  const [precioVenta, setPrecioVenta] = useState("");

  const cargar = useCallback(async () => {
    setError(null);
    try {
      setActivo(await obtenerActivo(id));
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    }
  }, [id]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  async function generar() {
    setError(null);
    setAviso(null);
    setOcupado("generar");
    try {
      const r = await generarAmortizacion(ejercicio, periodo);
      setAviso(`${r.n} amortización(es) generada(s).`);
      await cargar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    } finally {
      setOcupado(null);
    }
  }

  async function baja() {
    setError(null);
    setAviso(null);
    setOcupado("baja");
    try {
      const r = await darDeBaja(id, {
        fecha_baja: fechaBaja,
        precio_venta: precioVenta || undefined,
        tipo: "venta",
      });
      setAviso(
        `Baja registrada: VNC ${r.valor_neto_contable} · resultado ${r.resultado} (asiento ${r.asiento_id.slice(0, 8)}…).`
      );
      await cargar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    } finally {
      setOcupado(null);
    }
  }

  async function editar(campo: "vida_util", valor: number) {
    setError(null);
    setOcupado("editar");
    try {
      await editarActivo(id, { [campo]: valor });
      await cargar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    } finally {
      setOcupado(null);
    }
  }

  if (!activo) {
    return (
      <main className="p-6 max-w-3xl mx-auto">
        {error && <p className="text-red-600">{error}</p>}
      </main>
    );
  }

  return (
    <main className="p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-2">
        <h1 className="text-xl font-semibold">
          {activo.numero_activo} — {activo.descripcion}
        </h1>
        <Link href="/inmovilizado" className="text-blue-600 underline text-sm">
          Volver
        </Link>
      </div>

      <div className="border rounded p-4 text-sm mb-6">
        <dl className="grid grid-cols-2 gap-y-2">
          <div>
            <dt className="text-gray-500">Estado</dt>
            <dd>{ETIQUETA_ESTADO[activo.estado] ?? activo.estado}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Coste amortizable</dt>
            <dd className="font-mono">{activo.coste_amortizable}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Amortizado acumulado</dt>
            <dd className="font-mono">
              {activo.amortizado_acumulado ?? "0.0000"}
            </dd>
          </div>
          <div>
            <dt className="text-gray-500">Vida útil (meses)</dt>
            <dd>
              {activo.vida_util}
              <input
                type="number"
                min={1}
                defaultValue={activo.vida_util}
                onBlur={(e) => {
                  const v = Number(e.target.value);
                  if (v !== activo.vida_util) editar("vida_util", v);
                }}
                className="border rounded px-2 py-0.5 ml-2 w-20"
              />
            </dd>
          </div>
          <div>
            <dt className="text-gray-500">Método</dt>
            <dd>
              {activo.metodo}
              {activo.porcentaje_regresivo && ` (${activo.porcentaje_regresivo}%)`}
            </dd>
          </div>
          <div>
            <dt className="text-gray-500">Fecha de alta</dt>
            <dd>{activo.fecha_alta}</dd>
          </div>
          {activo.fecha_baja && (
            <div>
              <dt className="text-gray-500">Fecha de baja</dt>
              <dd>{activo.fecha_baja}</dd>
            </div>
          )}
        </dl>
      </div>

      {error && <p className="text-red-600 mb-4">{error}</p>}
      {aviso && <p className="text-emerald-700 mb-4">{aviso}</p>}

      {activo.estado === "en_uso" && (
        <>
          <section className="border rounded p-4 mb-6">
            <h2 className="font-semibold mb-2">Generar amortización</h2>
            <div className="flex items-end gap-3 text-sm">
              <label className="block">
                <span>Ejercicio</span>
                <input
                  type="number"
                  value={ejercicio}
                  onChange={(e) => setEjercicio(Number(e.target.value))}
                  className="border rounded px-3 py-1 mt-1 w-28"
                />
              </label>
              <label className="block">
                <span>Período (mes)</span>
                <input
                  type="number"
                  min={1}
                  max={12}
                  value={periodo}
                  onChange={(e) => setPeriodo(Number(e.target.value))}
                  className="border rounded px-3 py-1 mt-1 w-28"
                />
              </label>
              <button
                onClick={generar}
                disabled={ocupado !== null}
                className="bg-blue-600 text-white rounded px-4 py-2 disabled:opacity-50"
              >
                {ocupado === "generar" ? "Generando…" : "Generar"}
              </button>
            </div>
          </section>

          <section className="border rounded p-4 mb-6">
            <h2 className="font-semibold mb-2">Dar de baja / venta</h2>
            <div className="flex items-end gap-3 text-sm">
              <label className="block">
                <span>Fecha de baja</span>
                <input
                  type="date"
                  value={fechaBaja}
                  onChange={(e) => setFechaBaja(e.target.value)}
                  className="border rounded px-3 py-1 mt-1"
                />
              </label>
              <label className="block">
                <span>Precio de venta (opcional)</span>
                <input
                  className="border rounded px-3 py-1 mt-1 w-32 font-mono"
                  value={precioVenta}
                  onChange={(e) => setPrecioVenta(e.target.value)}
                  placeholder="0.0000"
                />
              </label>
              <button
                onClick={() => {
                  if (window.confirm("Confirmas la baja del activo?")) baja();
                }}
                disabled={ocupado !== null || !fechaBaja}
                className="bg-red-600 text-white rounded px-4 py-2 disabled:opacity-50"
              >
                {ocupado === "baja" ? "Dando de baja…" : "Dar de baja"}
              </button>
            </div>
          </section>
        </>
      )}

      <section className="border rounded p-4">
        <h2 className="font-semibold mb-2">Plan de amortización</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500">
              <th className="p-1">Período</th>
              <th className="p-1">Cuota</th>
              <th className="p-1">Acumulado</th>
              <th className="p-1">Estado</th>
            </tr>
          </thead>
          <tbody>
            {(activo.plan ?? []).map((f, i) => (
              <tr key={i} className="border-t">
                <td className="p-1 font-mono">
                  {f.ejercicio}-{String(f.periodo).padStart(2, "0")}
                </td>
                <td className="p-1 font-mono">{f.cuota}</td>
                <td className="p-1 font-mono">{f.acumulado}</td>
                <td className="p-1">{f.estado === "amortizado" ? "Amortizado" : "Pendiente"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}