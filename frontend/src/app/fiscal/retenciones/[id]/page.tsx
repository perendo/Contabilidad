"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  contabilizarLiquidacion,
  descargarModelo111,
  descargarModelo115,
  formatearImporte,
  generarModelo111,
  generarModelo115,
  listarRetenciones,
  obtenerLiquidacion,
  type DetalleLiquidacion,
  type RetencionPeriodo,
  type TipoRetencion,
} from "@/components/fiscal/api";
import { suscribirEmpresa } from "@/components/treasury/empresa";

const ETIQUETAS_TIPO: Record<TipoRetencion, string> = {
  IRPF_PROFESIONALES: "Profesionales",
  IRPF_ARRENDAMIENTOS: "Arrendamientos",
  IRPF_OBRAS: "Obras",
  IRPF_OTROS: "Otros",
};

function fechaFinTrimestre(ejercicio: number, trimestre: number): string {
  const fines = ["03-31", "06-30", "09-30", "12-31"];
  return `${ejercicio}-${fines[trimestre - 1] ?? "12-31"}`;
}

export default function DetalleLiquidacionPage() {
  const { id } = useParams<{ id: string }>();
  const [liquidacion, setLiquidacion] = useState<DetalleLiquidacion | null>(null);
  const [retenciones, setRetenciones] = useState<RetencionPeriodo[]>([]);
  const [cargando, setCargando] = useState(true);
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [descargandoId, setDescargandoId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mensaje, setMensaje] = useState<string | null>(null);
  const [fechaAsiento, setFechaAsiento] = useState("");
  const [cuentaBanco, setCuentaBanco] = useState("5720000");
  const [modelo111Id, setModelo111Id] = useState<string | null>(null);
  const [modelo115Id, setModelo115Id] = useState<string | null>(null);
  const [revisionEmpresa, setRevisionEmpresa] = useState(0);
  const periodo = liquidacion
    ? liquidacion.periodo || `${liquidacion.ejercicio}-Q${liquidacion.trimestre}`
    : "";

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const [resultado, detalleRetenciones] = await Promise.all([
        obtenerLiquidacion(id),
        listarRetenciones(id),
      ]);
      setLiquidacion(resultado);
      setRetenciones(
        detalleRetenciones.length > 0 ? detalleRetenciones : resultado.retenciones ?? []
      );
      setModelo111Id(resultado.modelo_111_id ?? null);
      setModelo115Id(resultado.modelo_115_id ?? null);
      setFechaAsiento((actual) => actual || fechaFinTrimestre(resultado.ejercicio, resultado.trimestre));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error al cargar la liquidación");
    } finally {
      setCargando(false);
    }
  }, [id]);

  useEffect(() => {
    void cargar();
  }, [cargar, revisionEmpresa]);

  useEffect(() => {
    return suscribirEmpresa(() => {
      setModelo111Id(null);
      setModelo115Id(null);
      setFechaAsiento("");
      setRevisionEmpresa((revision) => revision + 1);
    });
  }, []);

  async function generar(tipo: "111" | "115") {
    setOcupado(`modelo-${tipo}`);
    setError(null);
    setMensaje(null);
    try {
      if (tipo === "111") {
        const modelo = await generarModelo111({ liquidacion_id: id });
        setModelo111Id(modelo.id);
        await cargar();
        setModelo111Id(modelo.id);
        setMensaje("Modelo 111 generado.");
      } else {
        const modelo = await generarModelo115({ liquidacion_id: id });
        setModelo115Id(modelo.id);
        await cargar();
        setModelo115Id(modelo.id);
        setMensaje("Modelo 115 generado.");
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : `Error al generar el modelo ${tipo}`);
    } finally {
      setOcupado(null);
    }
  }

  async function descargar(tipo: "111" | "115") {
    const modeloId = tipo === "111" ? modelo111Id : modelo115Id;
    if (!modeloId) return;
    setDescargandoId(modeloId);
    setError(null);
    setMensaje(null);
    try {
      if (tipo === "111") {
        await descargarModelo111(modeloId, `modelo-111-${modeloId}.csv`);
      } else {
        await descargarModelo115(modeloId, `modelo-115-${modeloId}.csv`);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : `Error al descargar el modelo ${tipo}`);
    } finally {
      setDescargandoId(null);
    }
  }

  async function contabilizar() {
    if (!liquidacion || !fechaAsiento || !cuentaBanco.trim()) return;
    const confirmado = window.confirm(
      `Se generará el asiento de la liquidación ${periodo} por ${formatearImporte(
        liquidacion.total_retenciones
      )} con cargo a la cuenta ${cuentaBanco.trim()}. ¿Deseas continuar?`
    );
    if (!confirmado) return;
    setOcupado("contabilizar");
    setError(null);
    setMensaje(null);
    try {
      await contabilizarLiquidacion(id, {
        fecha_asiento: fechaAsiento,
        cuenta_banco: cuentaBanco.trim(),
      });
      await cargar();
      setMensaje("Liquidación contabilizada.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error al contabilizar la liquidación");
    } finally {
      setOcupado(null);
    }
  }

  if (cargando) {
    return <main className="p-8 text-center text-gray-500">Cargando liquidación…</main>;
  }

  if (!liquidacion) {
    return (
      <main className="space-y-4 p-6">
        <p className="text-red-600">{error || "Liquidación no encontrada"}</p>
        <Link href="/fiscal/retenciones" className="text-blue-600 underline">
          Volver al listado
        </Link>
      </main>
    );
  }

  const liquidado = liquidacion.estado === "liquidado";

  return (
    <main className="space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="text-xs text-gray-500">
            <Link href="/fiscal/retenciones" className="hover:underline">
              Retenciones IRPF
            </Link>{" "}
            / {periodo}
          </div>
          <h1 className="text-2xl font-bold">Liquidación {periodo}</h1>
        </div>
        <span
          className={`rounded px-3 py-1 text-sm font-semibold ${
            liquidado ? "bg-green-100 text-green-800" : "bg-blue-100 text-blue-800"
          }`}
        >
          {liquidacion.estado}
        </span>
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

      <section className="grid grid-cols-1 gap-4 rounded border bg-white p-6 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <p className="text-sm text-gray-500">Base de retenciones</p>
          <p className="font-mono text-lg font-semibold">
            {liquidacion.total_base_retenciones
              ? formatearImporte(liquidacion.total_base_retenciones)
              : "—"}
          </p>
        </div>
        <div>
          <p className="text-sm text-gray-500">Total retenciones</p>
          <p className="font-mono text-lg font-semibold text-blue-700">
            {formatearImporte(liquidacion.total_retenciones)}
          </p>
        </div>
        <div>
          <p className="text-sm text-gray-500">Perceptores</p>
          <p className="text-lg font-semibold">{liquidacion.n_perceptores ?? "—"}</p>
        </div>
        <div>
          <p className="text-sm text-gray-500">Fecha de liquidación</p>
          <p className="text-lg font-semibold">{liquidacion.fecha_liquidacion || "—"}</p>
        </div>
        <div>
          <p className="text-sm text-gray-500">Asiento</p>
          <p className="break-all font-mono text-xs">{liquidacion.asiento_id || "—"}</p>
        </div>
        <div>
          <p className="text-sm text-gray-500">Modelo 111</p>
          <p className="break-all font-mono text-xs">{modelo111Id || "No generado"}</p>
        </div>
        <div>
          <p className="text-sm text-gray-500">Modelo 115</p>
          <p className="break-all font-mono text-xs">{modelo115Id || "No generado"}</p>
        </div>
      </section>

      {liquidacion.notas && (
        <div className="rounded border bg-white p-4 text-sm">
          <span className="font-semibold">Notas: </span>
          <span className="whitespace-pre-wrap">{liquidacion.notas}</span>
        </div>
      )}

      <section className="rounded border bg-white p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Modelos 111 y 115</h2>
            <p className="text-sm text-gray-500">
              Genera el soporte del trimestre y descarga el fichero generado.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void generar("111")}
              disabled={ocupado !== null}
              className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {ocupado === "modelo-111" ? "Generando 111…" : "Generar modelo 111"}
            </button>
            <button
              type="button"
              onClick={() => void generar("115")}
              disabled={ocupado !== null}
              className="rounded bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {ocupado === "modelo-115" ? "Generando 115…" : "Generar modelo 115"}
            </button>
            <button
              type="button"
              onClick={() => void descargar("111")}
              disabled={!modelo111Id || descargandoId !== null}
              className="rounded border px-4 py-2 text-sm font-semibold text-blue-700 hover:bg-blue-50 disabled:opacity-40"
            >
              {descargandoId === modelo111Id ? "Descargando 111…" : "Descargar 111"}
            </button>
            <button
              type="button"
              onClick={() => void descargar("115")}
              disabled={!modelo115Id || descargandoId !== null}
              className="rounded border px-4 py-2 text-sm font-semibold text-blue-700 hover:bg-blue-50 disabled:opacity-40"
            >
              {descargandoId === modelo115Id ? "Descargando 115…" : "Descargar 115"}
            </button>
          </div>
        </div>
      </section>

      <section className="overflow-x-auto rounded border bg-white">
        <div className="border-b px-4 py-3">
          <h2 className="text-lg font-semibold">Retenciones por perceptor</h2>
        </div>
        <table className="w-full min-w-[1000px] text-sm">
          <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-3">Perceptor</th>
              <th className="px-4 py-3">NIF</th>
              <th className="px-4 py-3">Tipo</th>
              <th className="px-4 py-3 text-right">Base</th>
              <th className="px-4 py-3 text-right">Tipo %</th>
              <th className="px-4 py-3 text-right">Retención</th>
              <th className="px-4 py-3">Facturas</th>
            </tr>
          </thead>
          <tbody>
            {retenciones.map((retencion) => (
              <tr key={retencion.id} className="border-t">
                <td className="px-4 py-3">{retencion.nombre}</td>
                <td className="px-4 py-3 font-mono text-xs">{retencion.nif || "Sin NIF"}</td>
                <td className="px-4 py-3">{ETIQUETAS_TIPO[retencion.tipo_retencion]}</td>
                <td className="px-4 py-3 text-right font-mono">
                  {formatearImporte(retencion.base_imponible)}
                </td>
                <td className="px-4 py-3 text-right font-mono">{retencion.tipo_porcentaje}%</td>
                <td className="px-4 py-3 text-right font-mono font-semibold">
                  {formatearImporte(retencion.retencion_practicada)}
                </td>
                <td className="max-w-xs px-4 py-3 text-xs text-gray-600">
                  {retencion.facturas?.length
                    ? retencion.facturas.map((factura) => factura.numero).join(", ")
                    : "—"}
                </td>
              </tr>
            ))}
            {retenciones.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-400">
                  No hay retenciones para este periodo.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      <section className="rounded border border-amber-200 bg-amber-50 p-6">
        <h2 className="text-lg font-semibold text-amber-950">Contabilización</h2>
        <p className="mt-1 text-sm text-amber-800">
          Se generará un asiento POSTED con Debe 4751 y Haber en la cuenta bancaria indicada.
          Esta acción requiere confirmación.
        </p>
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="block text-sm font-semibold text-amber-950">
            Fecha del asiento
            <input
              type="date"
              required
              value={fechaAsiento}
              onChange={(e) => setFechaAsiento(e.target.value)}
              className="mt-1 block rounded border bg-white p-2"
            />
          </label>
          <label className="block text-sm font-semibold text-amber-950">
            Cuenta banco
            <input
              type="text"
              required
              maxLength={20}
              value={cuentaBanco}
              onChange={(e) => setCuentaBanco(e.target.value)}
              className="mt-1 block w-40 rounded border bg-white p-2 font-mono"
            />
          </label>
          <button
            type="button"
            onClick={() => void contabilizar()}
            disabled={liquidado || ocupado !== null || !fechaAsiento || !cuentaBanco.trim()}
            className="rounded bg-amber-700 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-800 disabled:opacity-50"
          >
            {ocupado === "contabilizar" ? "Contabilizando…" : "Contabilizar liquidación"}
          </button>
        </div>
      </section>
    </main>
  );
}
