"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../../../components/treasury/api";
import { get, post } from "../../../services/client";
import { formatearMoneda } from "@/lib/formato";

interface Movimiento {
  id: string;
  concepto: string;
  importe: string;
  signo: string;
}

interface Apunte {
  id: string;
  cuenta: string;
  debe: string;
  haber: string;
  descripcion: string | null;
}

interface Informe {
  id: string;
  estado: string;
  saldo_banco: string;
  saldo_libros: string;
  diferencia: string;
  pendientes: {
    movimientos_sin_cruzar: Movimiento[];
    apuntes_sin_extracto: Apunte[];
  };
}

interface Propuesta {
  id: string;
  movimiento_id: string;
  apunte_id: string;
  importe: string;
  prioridad: string;
}

export default function DetalleConciliacionPage() {
  const params = useParams<{ id: string }>();
  const [informe, setInforme] = useState<Informe | null>(null);
  const [propuestas, setPropuestas] = useState<Propuesta[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);
  const [mensajeExito, setMensajeExito] = useState<string | null>(null);

  // Selección manual para cruce
  const [movSeleccionadoId, setMovSeleccionadoId] = useState<string | null>(null);
  const [apunteSeleccionadoId, setApunteSeleccionadoId] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setError(null);
    try {
      setInforme(await get<Informe>(`/api/v1/conciliaciones/${params.id}`));
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }, [params.id]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  // Generar propuestas automáticas de casación
  async function proponer() {
    setError(null);
    setMensajeExito(null);
    setCargando(true);
    try {
      const cuerpo = await post<{ propuestas: Propuesta[] }>(
        `/api/v1/conciliaciones/${params.id}/propuestas`
      );
      setPropuestas(cuerpo.propuestas || []);
      if ((cuerpo.propuestas || []).length === 0) {
        setMensajeExito("No se detectaron nuevas coincidencias automáticas pendientes.");
      } else {
        setMensajeExito(`Se han encontrado ${cuerpo.propuestas.length} propuestas de casación.`);
      }
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    } finally {
      setCargando(false);
    }
  }

  // Confirmar una propuesta automática
  async function confirmar(p: Propuesta) {
    setError(null);
    try {
      await post(`/api/v1/conciliaciones/${params.id}/cruces`, {
        cruces: [{ movimiento_id: p.movimiento_id, apunte_id: p.apunte_id, origen: "auto" }],
      });
      setPropuestas((prev) => prev.filter((x) => x.id !== p.id));
      await cargar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }

  // Casación manual
  async function cruzarManualmente() {
    if (!movSeleccionadoId || !apunteSeleccionadoId) return;
    setError(null);
    try {
      await post(`/api/v1/conciliaciones/${params.id}/cruces`, {
        cruces: [{ movimiento_id: movSeleccionadoId, apunte_id: apunteSeleccionadoId, origen: "manual" }],
      });
      setMovSeleccionadoId(null);
      setApunteSeleccionadoId(null);
      await cargar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }

  // Cerrar y archivar conciliación
  async function cerrar() {
    if (!window.confirm("¿Confirmas que deseas cerrar y archivar esta conciliación bancaria?")) return;
    setError(null);
    try {
      await post(`/api/v1/conciliaciones/${params.id}/cerrar`);
      await cargar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }

  const cuadrada = informe?.diferencia === "0.0000" || Number(informe?.diferencia) === 0;

  return (
    <main className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <Link href="/conciliacion" className="text-xs text-blue-600 hover:underline">
              ← Volver a Conciliaciones
            </Link>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 mt-1">
            Sesión de Conciliación Bancaria
          </h1>
          <p className="text-xs text-slate-500 font-mono mt-0.5">ID: {params.id}</p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={proponer}
            disabled={cargando || informe?.estado === "cerrada"}
            className="bg-blue-600 hover:bg-blue-700 text-white rounded-lg px-4 py-2 text-xs font-bold shadow-sm transition-colors disabled:opacity-50 flex items-center gap-1.5"
          >
            <span>⚡ Generar Propuestas Automáticas</span>
          </button>
          <button
            onClick={cerrar}
            disabled={informe?.estado === "cerrada"}
            className="bg-slate-900 hover:bg-slate-800 text-white rounded-lg px-4 py-2 text-xs font-bold shadow-sm transition-colors disabled:opacity-50"
          >
            Cerrar y Archivar
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-rose-700 text-xs font-medium">
          {error}
        </div>
      )}

      {mensajeExito && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-xl text-emerald-800 text-xs font-medium">
          {mensajeExito}
        </div>
      )}

      {/* TARJETA DE SALDOS Y ESTADO */}
      {informe && (
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div className="space-y-1">
            <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Saldo Extracto (Banco)</div>
            <div className="text-lg font-mono font-bold text-slate-900">{formatearMoneda(informe.saldo_banco, true)}</div>
          </div>
          <div className="space-y-1">
            <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Saldo Libros (Contable)</div>
            <div className="text-lg font-mono font-bold text-slate-900">{formatearMoneda(informe.saldo_libros, true)}</div>
          </div>
          <div className="space-y-1">
            <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Diferencia a Cuadrar</div>
            <div className={`text-lg font-mono font-bold ${cuadrada ? "text-emerald-700" : "text-amber-700"}`}>
              {formatearMoneda(informe.diferencia, true)}
            </div>
          </div>
          <div className="space-y-1">
            <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Estado de Sesión</div>
            <div className="inline-block px-2.5 py-1 rounded text-xs font-bold uppercase bg-slate-100 text-slate-800 border border-slate-300">
              {informe.estado}
            </div>
          </div>
        </div>
      )}

      {/* PROPUESTAS AUTOMÁTICAS DETECTADAS */}
      {propuestas.length > 0 && (
        <section className="bg-amber-50/60 border border-amber-200 rounded-2xl p-5 space-y-3">
          <h2 className="text-xs font-bold uppercase tracking-wider text-amber-900 flex items-center justify-between">
            <span>Propuestas de Casación Automática Encontradas ({propuestas.length})</span>
            <span className="text-[11px] text-amber-700 font-normal">Pulsa para confirmar el cruce</span>
          </h2>
          <div className="space-y-2">
            {propuestas.map((p) => (
              <div
                key={p.id}
                className="bg-white border border-amber-200 rounded-xl p-3 flex flex-wrap items-center justify-between gap-3 text-xs shadow-sm"
              >
                <div className="flex items-center gap-3">
                  <span className="bg-amber-100 text-amber-900 font-bold px-2 py-0.5 rounded text-[10px] uppercase font-mono">
                    Prioridad: {p.prioridad}
                  </span>
                  <span className="font-mono text-slate-700">Movimiento #{p.movimiento_id.slice(0, 8)}</span>
                  <span className="text-slate-400">↔</span>
                  <span className="font-mono text-slate-700">Apunte #{p.apunte_id.slice(0, 8)}</span>
                  <span className="font-mono font-bold text-slate-900">Importe: {formatearMoneda(p.importe, true)}</span>
                </div>
                <button
                  type="button"
                  onClick={() => confirmar(p)}
                  className="px-3 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded font-bold text-xs shadow-sm transition-colors"
                >
                  ✓ Aceptar Cruce
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* CASACIÓN MANUAL Y LISTAS PENDIENTES */}
      {informe && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Movimientos del extracto sin casar */}
          <section className="bg-white border border-slate-200 rounded-2xl p-5 space-y-3 shadow-sm">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
              <h3 className="font-bold text-xs uppercase text-slate-800 tracking-wider">
                1. Movimientos Extracto Sin Casar ({informe.pendientes.movimientos_sin_cruzar.length})
              </h3>
            </div>
            {informe.pendientes.movimientos_sin_cruzar.length === 0 ? (
              <p className="text-xs text-slate-500 italic py-4 text-center">Todos los movimientos del extracto están casados.</p>
            ) : (
              <ul className="space-y-2 max-h-96 overflow-y-auto divide-y divide-slate-100">
                {informe.pendientes.movimientos_sin_cruzar.map((m) => {
                  const seleccionado = movSeleccionadoId === m.id;
                  return (
                    <li
                      key={m.id}
                      onClick={() => setMovSeleccionadoId(seleccionado ? null : m.id)}
                      className={`p-3 rounded-xl cursor-pointer transition-colors text-xs flex items-center justify-between ${
                        seleccionado
                          ? "bg-blue-50 border-2 border-blue-500 shadow-sm"
                          : "hover:bg-slate-50 border border-slate-100"
                      }`}
                    >
                      <div className="truncate pr-2">
                        <div className="font-medium text-slate-900 truncate">{m.concepto}</div>
                        <div className="text-[10px] text-slate-400 font-mono">Signo: {m.signo} · ID: {m.id.slice(0, 8)}</div>
                      </div>
                      <div className="font-mono font-bold text-slate-900 shrink-0">{formatearMoneda(m.importe, true)}</div>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          {/* Apuntes contables sin extracto */}
          <section className="bg-white border border-slate-200 rounded-2xl p-5 space-y-3 shadow-sm">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
              <h3 className="font-bold text-xs uppercase text-slate-800 tracking-wider">
                2. Apuntes Contables Sin Casar ({informe.pendientes.apuntes_sin_extracto.length})
              </h3>
            </div>
            {informe.pendientes.apuntes_sin_extracto.length === 0 ? (
              <p className="text-xs text-slate-500 italic py-4 text-center">Todos los apuntes contables están casados.</p>
            ) : (
              <ul className="space-y-2 max-h-96 overflow-y-auto divide-y divide-slate-100">
                {informe.pendientes.apuntes_sin_extracto.map((a) => {
                  const seleccionado = apunteSeleccionadoId === a.id;
                  const importe = Number(a.debe) > 0 ? a.debe : a.haber;
                  return (
                    <li
                      key={a.id}
                      onClick={() => setApunteSeleccionadoId(seleccionado ? null : a.id)}
                      className={`p-3 rounded-xl cursor-pointer transition-colors text-xs flex items-center justify-between ${
                        seleccionado
                          ? "bg-blue-50 border-2 border-blue-500 shadow-sm"
                          : "hover:bg-slate-50 border border-slate-100"
                      }`}
                    >
                      <div className="truncate pr-2">
                        <div className="font-medium text-slate-900 truncate">{a.descripcion || `Cuenta ${a.cuenta}`}</div>
                        <div className="text-[10px] text-slate-400 font-mono">Cuenta {a.cuenta} · ID: {a.id.slice(0, 8)}</div>
                      </div>
                      <div className="font-mono font-bold text-slate-900 shrink-0">{formatearMoneda(importe, true)}</div>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>
      )}

      {/* BOTÓN DE CASACIÓN MANUAL CUANDO SE SELECCIONAN AMBOS */}
      {movSeleccionadoId && apunteSeleccionadoId && (
        <div className="sticky bottom-4 bg-slate-900 text-white p-4 rounded-2xl shadow-2xl flex items-center justify-between border border-slate-800">
          <div className="text-xs">
            <span>Has seleccionado un movimiento bancario y un apunte contable para emparejar.</span>
          </div>
          <button
            type="button"
            onClick={cruzarManualmente}
            className="px-5 py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-xl text-xs transition-colors shadow-md"
          >
            ✓ Casar Manualmente Selección
          </button>
        </div>
      )}
    </main>
  );
}
