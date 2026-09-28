"use client";

import { useState } from "react";
import {
  ApiError,
  crearRemesa,
  formatearImporte,
  type Remesa,
  type RemesaFormato,
} from "../../../components/treasury/api";

interface VencimientoCandidato {
  id: string;
  recibo_num: string;
  importe: string;
  fecha_vencimiento: string;
  iban: string;
}

export default function NuevaRemesaPage() {
  const [formato, setFormato] = useState<RemesaFormato>("SEPA_DD");
  const [tipoAdeudo, setTipoAdeudo] = useState<"CORE" | "B2B">("CORE");
  const [fechaDesde, setFechaDesde] = useState("");
  const [fechaHasta, setFechaHasta] = useState("");
  const [cliente, setCliente] = useState("");
  const [banco, setBanco] = useState("");
  const [candidatos, setCandidatos] = useState<VencimientoCandidato[]>([]);
  const [seleccionados, setSeleccionados] = useState<Set<string>>(new Set());
  const [cargando, setCargando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const [creada, setCreada] = useState<Remesa | null>(null);

  async function buscarVencimientos() {
    setCargando(true);
    setAviso(null);
    try {
      const params = new URLSearchParams({ pendientes: "true" });
      if (fechaDesde) params.set("fecha_desde", fechaDesde);
      if (fechaHasta) params.set("fecha_hasta", fechaHasta);
      if (cliente) params.set("tercero_id", cliente);
      if (banco) params.set("banco", banco);
      const respuesta = await fetch(`/api/v1/vencimientos?${params.toString()}`);
      if (!respuesta.ok) {
        throw new ApiError(respuesta.status, "No se pudo consultar vencimientos");
      }
      const cuerpo = (await respuesta.json()) as { items: VencimientoCandidato[] };
      setCandidatos(cuerpo.items);
    } catch (error) {
      if (error instanceof ApiError) {
        setAviso(error.message);
      } else {
        setAviso("Vencimientos aún no disponibles: este catálogo llega con SPEC-011.");
        setCandidatos([]);
      }
    } finally {
      setCargando(false);
    }
  }

  function alternar(id: string, seleccion: boolean) {
    setSeleccionados((previos) => {
      const siguientes = new Set(previos);
      if (seleccion) siguientes.add(id);
      else siguientes.delete(id);
      return siguientes;
    });
  }

  const totalSeleccionado = seleccionados.size
    ? seleccionados
        .values()
        .reduce(
          (acumulado, id) =>
            acumulado +
            Number(
              candidatos.find((c) => c.id === id)?.importe ?? "0"
            ),
          0
        )
    : 0;

  async function enviar() {
    setAviso(null);
    try {
      const remesa = await crearRemesa({
        formato,
        tipo_adeudo: tipoAdeudo,
        recibo_ids: Array.from(seleccionados),
      });
      setCreada(remesa);
    } catch (error) {
      if (error instanceof ApiError) {
        setAviso(error.message);
      } else {
        setAviso("Error inesperado al crear la remesa");
      }
    }
  }

  return (
    <main className="p-6 max-w-4xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Nueva remesa de cobros</h1>

      <section className="border rounded p-4 mb-4">
        <h2 className="font-medium mb-2">Configuración</h2>
        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            Formato
            <select
              className="w-full border rounded p-1"
              value={formato}
              onChange={(e) => setFormato(e.target.value as RemesaFormato)}
            >
              <option value="SEPA_DD">SEPA DD (PAIN.008)</option>
              <option value="CSB_19_19">CSB 19.19</option>
            </select>
          </label>
          <label className="block">
            Tipo de adeudo
            <select
              className="w-full border rounded p-1"
              value={tipoAdeudo}
              onChange={(e) =>
                setTipoAdeudo(e.target.value as "CORE" | "B2B")
              }
            >
              <option value="CORE">CORE</option>
              <option value="B2B">B2B</option>
            </select>
          </label>
        </div>
      </section>

      <section className="border rounded p-4 mb-4">
        <h2 className="font-medium mb-2">Selección de recibos</h2>
        <div className="grid grid-cols-2 gap-3 mb-2">
          <label className="block">
            Fecha desde
            <input
              type="date"
              className="w-full border rounded p-1"
              value={fechaDesde}
              onChange={(e) => setFechaDesde(e.target.value)}
            />
          </label>
          <label className="block">
            Fecha hasta
            <input
              type="date"
              className="w-full border rounded p-1"
              value={fechaHasta}
              onChange={(e) => setFechaHasta(e.target.value)}
            />
          </label>
          <label className="block">
            Cliente (tercero_id)
            <input
              className="w-full border rounded p-1"
              value={cliente}
              onChange={(e) => setCliente(e.target.value)}
            />
          </label>
          <label className="block">
            Banco (prefijo IBAN)
            <input
              className="w-full border rounded p-1"
              value={banco}
              onChange={(e) => setBanco(e.target.value)}
            />
          </label>
        </div>
        <button
          className="bg-slate-800 text-white rounded px-3 py-1"
          onClick={buscarVencimientos}
          disabled={cargando}
        >
          {cargando ? "Buscando…" : "Buscar pendientes"}
        </button>
        {aviso && <p className="mt-2 text-sm text-amber-700">{aviso}</p>}

        {candidatos.length > 0 && (
          <table className="w-full mt-3 text-sm">
            <thead>
              <tr className="text-left border-b">
                <th />
                <th>Recibo</th>
                <th>Vencimiento</th>
                <th>Importe</th>
                <th>IBAN</th>
              </tr>
            </thead>
            <tbody>
              {candidatos.map((candidato) => (
                <tr key={candidato.id} className="border-b">
                  <td>
                    <input
                      type="checkbox"
                      checked={seleccionados.has(candidato.id)}
                      onChange={(e) => alternar(candidato.id, e.target.checked)}
                    />
                  </td>
                  <td>{candidato.recibo_num}</td>
                  <td>{candidato.fecha_vencimiento}</td>
                  <td>{formatearImporte(candidato.importe)}</td>
                  <td>{candidato.iban}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="mt-2 text-sm">
          Seleccionados: {seleccionados.size} · Total{" "}
          {formatearImporte(totalSeleccionado.toFixed(4))}
        </p>
      </section>

      <button
        className="bg-blue-600 text-white rounded px-4 py-2"
        onClick={enviar}
        disabled={seleccionados.size === 0}
      >
        Crear remesa
      </button>

      {creada && (
        <div className="mt-4 border border-green-300 rounded p-4">
          <p className="font-medium">Remesa {creada.numero_remesa} creada</p>
          <p>
            Estado: {creada.estado} · Importe {formatearImporte(creada.importe_total)}
          </p>
          <a className="text-blue-600 underline" href={`/remesas/${creada.id}`}>
            Ver detalle
          </a>
        </div>
      )}
    </main>
  );
}