"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import {
  ApiError,
  agregarAjuste,
  contabilizarCalculo,
  eliminarAjuste,
  formatearImporte,
  obtenerCalculo,
  recalcularCalculo,
  type AjusteExtracontable,
  type DetalleCalculo,
  type TipoAjuste,
} from "@/components/fiscal/api";

const TIPOS_AJUSTE: TipoAjuste[] = [
  "AJUSTE_POSITIVO",
  "AJUSTE_NEGATIVO",
  "DEDUCCION",
  "BONIFICACION",
];

const ETIQUETAS: Record<TipoAjuste, string> = {
  AJUSTE_POSITIVO: "Ajuste positivo",
  AJUSTE_NEGATIVO: "Ajuste negativo",
  DEDUCCION: "Deducción",
  BONIFICACION: "Bonificación",
};

export default function DetalleCalculoPage() {
  const { id } = useParams<{ id: string }>();
  const [calculo, setCalculo] = useState<DetalleCalculo | null>(null);
  const [cargando, setCargando] = useState(true);
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mensaje, setMensaje] = useState<string | null>(null);

  const [tipo, setTipo] = useState<TipoAjuste>("AJUSTE_POSITIVO");
  const [descripcion, setDescripcion] = useState("");
  const [referencia, setReferencia] = useState("");
  const [importe, setImporte] = useState("");
  const [fechaAsiento, setFechaAsiento] = useState("");

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const resultado = await obtenerCalculo(id);
      setCalculo(resultado);
      setFechaAsiento((actual) => actual || `${resultado.ejercicio}-12-31`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error al cargar el cálculo");
    } finally {
      setCargando(false);
    }
  }, [id]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  async function agregar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    setOcupado("agregar");
    setError(null);
    setMensaje(null);
    try {
      await agregarAjuste(id, {
        tipo,
        descripcion: descripcion.trim(),
        referencia_normativa: referencia.trim() || null,
        importe: importe.trim(),
      });
      setDescripcion("");
      setReferencia("");
      setImporte("");
      await cargar();
      setMensaje("Ajuste añadido.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error al añadir el ajuste");
    } finally {
      setOcupado(null);
    }
  }

  async function borrar(ajuste: AjusteExtracontable) {
    if (!window.confirm(`Eliminar el ajuste «${ajuste.descripcion}»?`)) return;
    setOcupado(`eliminar-${ajuste.id}`);
    setError(null);
    setMensaje(null);
    try {
      await eliminarAjuste(id, ajuste.id);
      await cargar();
      setMensaje("Ajuste eliminado.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error al eliminar el ajuste");
    } finally {
      setOcupado(null);
    }
  }

  async function recalcular() {
    if (!calculo) return;
    if (!window.confirm("¿Recalcular el Impuesto sobre Sociedades con los ajustes actuales?")) return;
    setOcupado("recalcular");
    setError(null);
    setMensaje(null);
    try {
      await recalcularCalculo(id, { ajustes: [], deducciones: [] });
      await cargar();
      setMensaje("Cálculo actualizado.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error al recalcular el cálculo");
    } finally {
      setOcupado(null);
    }
  }

  async function contabilizar() {
    if (!calculo || !fechaAsiento) return;
    const confirmado = window.confirm(
      `Se generará el asiento del IS con fecha ${fechaAsiento}. ¿Deseas continuar?`
    );
    if (!confirmado) return;
    setOcupado("contabilizar");
    setError(null);
    setMensaje(null);
    try {
      await contabilizarCalculo(id, { fecha_asiento: fechaAsiento });
      await cargar();
      setMensaje("Impuesto sobre Sociedades contabilizado.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error al contabilizar el cálculo");
    } finally {
      setOcupado(null);
    }
  }

  if (cargando) {
    return <main className="p-8 text-center text-gray-500">Cargando cálculo…</main>;
  }

  if (!calculo) {
    return (
      <main className="space-y-4 p-6">
        <p className="text-red-600">{error || "Cálculo no encontrado"}</p>
        <Link href="/fiscal/impuesto-sociedades" className="text-blue-600 underline">
          Volver al listado
        </Link>
      </main>
    );
  }

  const bloqueado = calculo.estado === "contabilizado";

  return (
    <main className="space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="text-xs text-gray-500">
            <Link href="/fiscal/impuesto-sociedades" className="hover:underline">
              Impuesto sobre Sociedades
            </Link>{" "}
            / Ejercicio {calculo.ejercicio}
          </div>
          <h1 className="text-2xl font-bold">Cálculo de IS</h1>
        </div>
        <span
          className={`rounded px-3 py-1 text-sm font-semibold ${
            bloqueado
              ? "bg-green-100 text-green-800"
              : "bg-blue-100 text-blue-800"
          }`}
        >
          {calculo.estado}
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

      <section className="grid grid-cols-1 gap-4 rounded border bg-white p-6 sm:grid-cols-2 lg:grid-cols-3">
        <div>
          <p className="text-sm text-gray-500">Resultado contable</p>
          <p className="font-mono text-lg font-semibold">
            {formatearImporte(calculo.resultado_contable)}
          </p>
        </div>
        <div>
          <p className="text-sm text-gray-500">Ajustes positivos</p>
          <p className="font-mono text-lg font-semibold">
            {formatearImporte(calculo.ajustes_positivos)}
          </p>
        </div>
        <div>
          <p className="text-sm text-gray-500">Ajustes negativos</p>
          <p className="font-mono text-lg font-semibold">
            {formatearImporte(calculo.ajustes_negativos)}
          </p>
        </div>
        <div>
          <p className="text-sm text-gray-500">Base imponible</p>
          <p className="font-mono text-lg font-semibold text-blue-700">
            {formatearImporte(calculo.base_imponible)}
          </p>
        </div>
        <div>
          <p className="text-sm text-gray-500">Tipo impositivo</p>
          <p className="font-mono text-lg font-semibold">
            {calculo.tipo_impositivo}%
          </p>
        </div>
        <div>
          <p className="text-sm text-gray-500">Cuota íntegra</p>
          <p className="font-mono text-lg font-semibold">
            {formatearImporte(calculo.cuota_integra)}
          </p>
        </div>
        <div>
          <p className="text-sm text-gray-500">Deducciones</p>
          <p className="font-mono text-lg font-semibold">
            {formatearImporte(calculo.deducciones)}
          </p>
        </div>
        <div>
          <p className="text-sm text-gray-500">Cuota líquida</p>
          <p className="font-mono text-lg font-semibold">
            {formatearImporte(calculo.cuota_liquida)}
          </p>
        </div>
        <div>
          <p className="text-sm text-gray-500">Pagos a cuenta (473)</p>
          <p className="font-mono text-lg font-semibold">
            {formatearImporte(calculo.pagos_a_cuenta)}
          </p>
        </div>
        <div>
          <p className="text-sm text-gray-500">Cuota diferencial</p>
          <p className="font-mono text-lg font-semibold text-amber-700">
            {formatearImporte(calculo.cuota_diferencial)}
          </p>
        </div>
        <div>
          <p className="text-sm text-gray-500">Asiento</p>
          <p className="break-all font-mono text-xs">{calculo.asiento_id || "—"}</p>
        </div>
        <div>
          <p className="text-sm text-gray-500">Modalidad</p>
          <p className="text-lg font-semibold">
            {calculo.provisional ? "Provisional" : "Definitiva"}
          </p>
        </div>
      </section>

      {calculo.notas && (
        <div className="rounded border bg-white p-4 text-sm">
          <span className="font-semibold">Notas: </span>
          <span className="whitespace-pre-wrap">{calculo.notas}</span>
        </div>
      )}

      <section className="overflow-hidden rounded border bg-white">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
          <h2 className="text-lg font-semibold">Ajustes y deducciones</h2>
          <button
            type="button"
            onClick={recalcular}
            disabled={bloqueado || ocupado !== null}
            className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {ocupado === "recalcular" ? "Recalculando…" : "Recalcular"}
          </button>
        </div>
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-3">Tipo</th>
              <th className="px-4 py-3">Descripción</th>
              <th className="px-4 py-3">Referencia</th>
              <th className="px-4 py-3 text-right">Importe</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {(calculo.ajustes ?? []).map((ajuste) => (
              <tr key={ajuste.id} className="border-t">
                <td className="px-4 py-3">{ETIQUETAS[ajuste.tipo]}</td>
                <td className="px-4 py-3">{ajuste.descripcion}</td>
                <td className="px-4 py-3 text-gray-500">
                  {ajuste.referencia_normativa || "—"}
                </td>
                <td className="px-4 py-3 text-right font-mono">{ajuste.importe}</td>
                <td className="px-4 py-3 text-right">
                  <button
                    type="button"
                    onClick={() => void borrar(ajuste)}
                    disabled={bloqueado || ocupado !== null}
                    className="text-red-600 underline disabled:opacity-40"
                  >
                    Eliminar
                  </button>
                </td>
              </tr>
            ))}
            {(calculo.ajustes ?? []).length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                  Todavía no hay ajustes.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      {!bloqueado && (
        <form onSubmit={agregar} className="space-y-4 rounded border bg-gray-50 p-6">
          <h2 className="text-lg font-semibold">Añadir ajuste o deducción</h2>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
            <label className="block text-sm font-semibold">
              Tipo
              <select
                value={tipo}
                onChange={(e) => setTipo(e.target.value as TipoAjuste)}
                className="mt-1 block w-full rounded border bg-white p-2"
              >
                {TIPOS_AJUSTE.map((valor) => (
                  <option key={valor} value={valor}>
                    {ETIQUETAS[valor]}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm font-semibold md:col-span-1">
              Importe
              <input
                type="text"
                required
                pattern="^\d+(\.\d{1,4})?$"
                value={importe}
                onChange={(e) => setImporte(e.target.value)}
                placeholder="0.0000"
                className="mt-1 block w-full rounded border bg-white p-2 font-mono"
              />
            </label>
            <label className="block text-sm font-semibold md:col-span-2">
              Descripción
              <input
                type="text"
                required
                maxLength={500}
                value={descripcion}
                onChange={(e) => setDescripcion(e.target.value)}
                className="mt-1 block w-full rounded border bg-white p-2"
              />
            </label>
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
            <label className="block text-sm font-semibold md:col-span-2">
              Referencia normativa (opcional)
              <input
                type="text"
                maxLength={255}
                value={referencia}
                onChange={(e) => setReferencia(e.target.value)}
                className="mt-1 block w-full rounded border bg-white p-2"
              />
            </label>
            <div className="flex items-end md:col-span-2">
              <button
                type="submit"
                disabled={ocupado !== null}
                className="rounded bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
              >
                {ocupado === "agregar" ? "Añadiendo…" : "Añadir ajuste"}
              </button>
            </div>
          </div>
        </form>
      )}

      <section className="rounded border border-amber-200 bg-amber-50 p-6">
        <h2 className="text-lg font-semibold text-amber-950">Contabilización</h2>
        <p className="mt-1 text-sm text-amber-800">
          Se generará un asiento POSTED con la cuenta 630 y la contrapartida fiscal
          correspondiente. Esta acción requiere confirmación.
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
          <button
            type="button"
            onClick={() => void contabilizar()}
            disabled={calculo.estado !== "calculado" || ocupado !== null}
            className="rounded bg-amber-700 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-800 disabled:opacity-50"
          >
            {ocupado === "contabilizar" ? "Contabilizando…" : "Contabilizar IS"}
          </button>
        </div>
      </section>
    </main>
  );
}
