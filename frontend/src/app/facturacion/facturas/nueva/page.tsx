"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import {
  crearFactura,
  emitirFactura,
  listarSeries,
  listarTerceros,
  type LineaFacturaInput,
  type SerieFactura,
  type TerceroResumen,
} from "../../../../components/invoicing/api";
import { ApiError } from "../../../../components/treasury/api";

interface LineaForm {
  descripcion: string;
  cantidad: string;
  precio_unitario: string;
  tipo_iva: string;
  tipo_recargo: string;
  tipo_irpf: string;
  base_irpf: string;
}

const LINEA_VACIA: LineaForm = {
  descripcion: "",
  cantidad: "1",
  precio_unitario: "0.0000",
  tipo_iva: "21",
  tipo_recargo: "0",
  tipo_irpf: "0",
  base_irpf: "0",
};

export default function NuevaFacturaPage() {
  const router = useRouter();
  const [series, setSeries] = useState<SerieFactura[]>([]);
  const [terceros, setTerceros] = useState<TerceroResumen[]>([]);
  const [tipo, setTipo] = useState("VENTA");
  const [serieId, setSerieId] = useState("");
  const [terceroId, setTerceroId] = useState("");
  const [fecha, setFecha] = useState("2026-03-01");
  const [ejercicio, setEjercicio] = useState(2026);
  const [concepto, setConcepto] = useState("");
  const [regimenCaja, setRegimenCaja] = useState(false);
  const [emitir, setEmitir] = useState(true);
  const [lineas, setLineas] = useState<LineaForm[]>([{ ...LINEA_VACIA }]);
  const [error, setError] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const cargar = useCallback(async () => {
    try {
      const [s, t] = await Promise.all([
        listarSeries(),
        listarTerceros(tipo === "VENTA" ? "cliente" : "proveedor"),
      ]);
      setSeries(s);
      setTerceros(t.items);
      if (s.length > 0 && !serieId) setSerieId(s[0].id);
      if (t.items.length > 0 && !terceroId) setTerceroId(t.items[0].id);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }, [tipo, serieId, terceroId]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  function actualizarLinea(idx: number, campo: keyof LineaForm, valor: string) {
    setLineas((prev) =>
      prev.map((l, i) => (i === idx ? { ...l, [campo]: valor } : l))
    );
  }

  async function guardar() {
    setError(null);
    setOcupado(true);
    try {
      const payloadLineas: LineaFacturaInput[] = lineas.map((l) => ({
        descripcion: l.descripcion,
        cantidad: l.cantidad,
        precio_unitario: l.precio_unitario,
        tipo_iva: l.tipo_iva,
        tipo_recargo: l.tipo_recargo,
        tipo_irpf: l.tipo_irpf,
        base_irpf: l.base_irpf,
      }));
      const factura = await crearFactura({
        serie_id: serieId,
        ejercicio,
        fecha,
        tipo,
        tercero_id: terceroId,
        concepto_global: concepto || undefined,
        regimen_caja: regimenCaja,
        lineas: payloadLineas,
      });
      if (emitir) await emitirFactura(factura.id);
      router.push(`/facturacion/facturas/${factura.id}`);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <main className="p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">Nueva factura</h1>
        <Link href="/facturacion/facturas" className="text-blue-700 underline">
          Volver
        </Link>
      </div>

      {error && <p className="text-red-600 mb-4">{error}</p>}

      <div className="grid grid-cols-2 gap-4 mb-4">
        <label className="block">
          <span className="text-sm">Tipo</span>
          <select
            value={tipo}
            onChange={(e) => setTipo(e.target.value)}
            className="border rounded px-2 py-1 mt-1 w-full"
          >
            <option value="VENTA">Venta</option>
            <option value="COMPRA">Compra</option>
          </select>
        </label>
        <label className="block">
          <span className="text-sm">Serie</span>
          <select
            value={serieId}
            onChange={(e) => setSerieId(e.target.value)}
            className="border rounded px-2 py-1 mt-1 w-full"
          >
            {series.map((s) => (
              <option key={s.id} value={s.id}>
                {s.codigo} ({s.estado})
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="text-sm">Tercero</span>
          <select
            value={terceroId}
            onChange={(e) => setTerceroId(e.target.value)}
            className="border rounded px-2 py-1 mt-1 w-full"
          >
            {terceros.map((t) => (
              <option key={t.id} value={t.id}>
                {t.nombre}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="text-sm">Fecha</span>
          <input
            type="date"
            value={fecha}
            onChange={(e) => {
              setFecha(e.target.value);
              if (e.target.value) setEjercicio(Number(e.target.value.slice(0, 4)));
            }}
            className="border rounded px-2 py-1 mt-1 w-full"
          />
        </label>
        <label className="block">
          <span className="text-sm">Ejercicio</span>
          <input
            type="number"
            value={ejercicio}
            onChange={(e) => setEjercicio(Number(e.target.value))}
            className="border rounded px-2 py-1 mt-1 w-full"
          />
        </label>
        <label className="block">
          <span className="text-sm">Concepto</span>
          <input
            value={concepto}
            onChange={(e) => setConcepto(e.target.value)}
            className="border rounded px-2 py-1 mt-1 w-full"
          />
        </label>
      </div>

      <label className="flex items-center gap-2 mb-4 text-sm">
        <input
          type="checkbox"
          checked={regimenCaja}
          onChange={(e) => setRegimenCaja(e.target.checked)}
        />
        Régimen especial de criterio de caja (IVA diferido)
      </label>

      <h2 className="font-medium mb-2">Líneas</h2>
      <table className="w-full text-sm mb-3">
        <thead className="bg-gray-100">
          <tr>
            <th className="text-left p-2">Descripción</th>
            <th className="p-2">Cantidad</th>
            <th className="p-2">Precio</th>
            <th className="p-2">IVA %</th>
            <th className="p-2">Recargo %</th>
            <th className="p-2">IRPF %</th>
            <th className="p-2">Base IRPF</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {lineas.map((l, i) => (
            <tr key={i} className="border-t">
              <td className="p-1">
                <input
                  value={l.descripcion}
                  onChange={(e) => actualizarLinea(i, "descripcion", e.target.value)}
                  className="border rounded px-2 py-1 w-full"
                />
              </td>
              <td className="p-1">
                <input
                  value={l.cantidad}
                  onChange={(e) => actualizarLinea(i, "cantidad", e.target.value)}
                  className="border rounded px-2 py-1 w-20"
                />
              </td>
              <td className="p-1">
                <input
                  value={l.precio_unitario}
                  onChange={(e) => actualizarLinea(i, "precio_unitario", e.target.value)}
                  className="border rounded px-2 py-1 w-28"
                />
              </td>
              <td className="p-1">
                <input
                  value={l.tipo_iva}
                  onChange={(e) => actualizarLinea(i, "tipo_iva", e.target.value)}
                  className="border rounded px-2 py-1 w-16"
                />
              </td>
              <td className="p-1">
                <input
                  value={l.tipo_recargo}
                  onChange={(e) => actualizarLinea(i, "tipo_recargo", e.target.value)}
                  className="border rounded px-2 py-1 w-16"
                />
              </td>
              <td className="p-1">
                <input
                  value={l.tipo_irpf}
                  onChange={(e) => actualizarLinea(i, "tipo_irpf", e.target.value)}
                  className="border rounded px-2 py-1 w-16"
                />
              </td>
              <td className="p-1">
                <input
                  value={l.base_irpf}
                  onChange={(e) => actualizarLinea(i, "base_irpf", e.target.value)}
                  className="border rounded px-2 py-1 w-24"
                />
              </td>
              <td className="p-1">
                <button
                  onClick={() =>
                    setLineas((prev) => prev.filter((_, j) => j !== i))
                  }
                  disabled={lineas.length === 1}
                  className="text-red-600 disabled:opacity-40"
                >
                  ×
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button
        onClick={() => setLineas((prev) => [...prev, { ...LINEA_VACIA }])}
        className="bg-gray-200 rounded px-3 py-1 mb-4"
      >
        Añadir línea
      </button>

      <div className="flex items-center gap-4">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={emitir}
            onChange={(e) => setEmitir(e.target.checked)}
          />
          Emitir al guardar
        </label>
        <button
          onClick={guardar}
          disabled={ocupado}
          className="bg-blue-600 text-white rounded px-4 py-2 disabled:opacity-50"
        >
          {ocupado ? "Guardando…" : emitir ? "Crear y emitir" : "Guardar borrador"}
        </button>
      </div>
    </main>
  );
}
