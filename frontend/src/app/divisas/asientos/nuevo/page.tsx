"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ApiError,
  crearAsientoDivisa,
  listarDivisas,
  listarTipos,
  type AsientoDivisa,
  type Divisa,
  type TipoCambio,
} from "@/components/forex/api";
import { sugerirCuentas, type CuentaSugerida } from "@/services/acct/api";

interface LineaEditor {
  key: number;
  cuenta_id: string;
  cuenta_label: string;
  es_debe: "debe" | "haber";
  importe: string;
}

export default function NuevoAsientoDivisaPage() {
  const [divisas, setDivisas] = useState<Divisa[]>([]);
  const [divisaId, setDivisaId] = useState("");
  const [fecha, setFecha] = useState("2026-10-01");
  const [concepto, setConcepto] = useState("Asiento en divisa");
  const [tipos, setTipos] = useState<TipoCambio[]>([]);
  const [tipoId, setTipoId] = useState("");
  const [ratioExplicito, setRatioExplicito] = useState("");
  const [lineas, setLineas] = useState<LineaEditor[]>([
    { key: 1, cuenta_id: "", cuenta_label: "", es_debe: "debe", importe: "" },
    { key: 2, cuenta_id: "", cuenta_label: "", es_debe: "haber", importe: "" },
  ]);
  const [sugerencias, setSugerencias] = useState<CuentaSugerida[]>([]);
  const [cuentaBuscada, setCuentaBuscada] = useState<Record<number, string>>({});
  const [resultado, setResultado] = useState<AsientoDivisa | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const datos = await listarDivisas();
        setDivisas(datos.items);
        if (datos.items.length > 0) {
          setDivisaId(datos.items[0].id);
          setTipos((await listarTipos({ divisa_id: datos.items[0].id })).items);
        }
      } catch (error) {
        setAviso(error instanceof ApiError ? error.message : "No se pudieron cargar divisas");
      }
    })();
  }, []);

  useEffect(() => {
    (async () => {
      setAviso(null);
      try {
        setTipos((await listarTipos({ divisa_id: divisaId })).items);
      } catch {
        setTipos([]);
      }
    })();
  }, [divisaId]);

  const cuentaSeleccionada = (linea: LineaEditor, sugerida: CuentaSugerida | undefined) => {
    if (!sugerida) return;
    setLineas((previas) =>
      previas.map((l) =>
        l.key === linea.key
          ? { ...l, cuenta_id: String(sugerida.id), cuenta_label: `${sugerida.code} ${sugerida.name}` }
          : l
      )
    );
    setSugerencias([]);
  };

  function buscarCuenta(linea: LineaEditor, valor: string) {
    setCuentaBuscada((prev) => ({ ...prev, [linea.key]: valor }));
    if (valor.trim().length < 1) {
      setSugerencias([]);
      return;
    }
    sugerirCuentas(valor)
      .then((res) => setSugerencias(res.items))
      .catch(() => setSugerencias([]));
  }

  function actualizarLinea(key: number, campo: Partial<LineaEditor>) {
    setLineas((previas) => previas.map((l) => (l.key === key ? { ...l, ...campo } : l)));
  }

  function añadirLinea() {
    const key = Date.now();
    setLineas((previas) => [
      ...previas,
      { key, cuenta_id: "", cuenta_label: "", es_debe: "haber", importe: "" },
    ]);
  }

  const totalDebe = lineas
    .filter((l) => l.es_debe === "debe")
    .reduce((ac, l) => ac + Number(l.importe || "0"), 0);
  const totalHaber = lineas
    .filter((l) => l.es_debe === "haber")
    .reduce((ac, l) => ac + Number(l.importe || "0"), 0);
  const ratio = tipoId ? undefined : ratioExplicito;
  const desequilibrado = Math.abs(totalDebe - totalHaber) > 0.0001;

  async function enviar() {
    setAviso(null);
    try {
      const body: {
        fecha: string;
        divisa_id: string;
        concepto: string;
        lineas: { cuenta_id: number; debe_divisa: string; haber_divisa: string }[];
        tipo_cambio_id?: string;
        tipo_ratio_explicito?: { ratio: string };
      } = {
        fecha,
        divisa_id: divisaId,
        concepto,
        lineas: lineas.map((l) => ({
          cuenta_id: Number(l.cuenta_id),
          debe_divisa: l.es_debe === "debe" ? l.importe || "0.0000" : "0.0000",
          haber_divisa: l.es_debe === "haber" ? l.importe || "0.0000" : "0.0000",
        })),
      };
      if (tipoId) body.tipo_cambio_id = tipoId;
      if (ratio) body.tipo_ratio_explicito = { ratio };
      setResultado(await crearAsientoDivisa(body));
    } catch (error) {
      setAviso(error instanceof ApiError ? error.message : "Error al crear el asiento");
    }
  }

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">
        Nuevo asiento en divisa{" "}
        <Link className="text-sm text-blue-600 underline" href="/divisas">
          divisas
        </Link>
      </h1>

      <section className="border rounded p-4 mb-4">
        <div className="grid grid-cols-3 gap-3">
          <label className="block">
            Divisa
            <select
              className="w-full border rounded p-1"
              value={divisaId}
              onChange={(e) => setDivisaId(e.target.value)}
            >
              {divisas.map((divisa) => (
                <option key={divisa.id} value={divisa.id}>
                  {divisa.codigo_iso}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            Fecha
            <input
              type="date"
              className="w-full border rounded p-1"
              value={fecha}
              onChange={(e) => setFecha(e.target.value)}
            />
          </label>
          <label className="block">
            Concepto
            <input
              className="w-full border rounded p-1"
              value={concepto}
              onChange={(e) => setConcepto(e.target.value)}
            />
          </label>
        </div>
        <div className="grid grid-cols-2 gap-3 mt-3">
          <label className="block">
            Tipo de cambio existente
            <select
              className="w-full border rounded p-1"
              value={tipoId}
              onChange={(e) => {
                setTipoId(e.target.value);
                if (e.target.value) setRatioExplicito("");
              }}
            >
              <option value="">— seleccionar —</option>
              {tipos.map((tipo) => (
                <option key={tipo.id} value={tipo.id}>
                  {tipo.fecha} · {tipo.ratio} ({tipo.sellado ? "sellado" : "editable"})
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            O ratio explícito (1 divisa = X funcional)
            <input
              className="w-full border rounded p-1"
              value={ratioExplicito}
              onChange={(e) => {
                setRatioExplicito(e.target.value);
                if (e.target.value) setTipoId("");
              }}
              placeholder="0.00000000"
            />
          </label>
        </div>
      </section>

      <section className="border rounded p-4 mb-4">
        <h2 className="font-medium mb-2">Líneas (importes en la divisa)</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left border-b">
              <th>Cuenta</th>
              <th className="w-20">Lado</th>
              <th className="w-32">Importe divisa</th>
              <th className="w-32">Funcional (preview)</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {lineas.map((linea) => (
              <tr key={linea.key} className="border-b">
                <td>
                  <input
                    className="border rounded p-1 w-full"
                    value={cuentaBuscada[linea.key] ?? linea.cuenta_label}
                    onChange={(e) => buscarCuenta(linea, e.target.value)}
                    placeholder="código o nombre"
                  />
                  {sugerencias.length > 0 && (
                    <ul className="border rounded bg-white text-xs mt-1">
                      {sugerencias.map((sug) => (
                        <li
                          key={sug.id}
                          className="px-2 py-1 hover:bg-slate-100 cursor-pointer"
                          onClick={() => cuentaSeleccionada(linea, sug)}
                        >
                          {sug.code} · {sug.name}
                        </li>
                      ))}
                    </ul>
                  )}
                </td>
                <td>
                  <select
                    className="border rounded p-1"
                    value={linea.es_debe}
                    onChange={(e) => actualizarLinea(linea.key, { es_debe: e.target.value as "debe" | "haber" })}
                  >
                    <option value="debe">Debe</option>
                    <option value="haber">Haber</option>
                  </select>
                </td>
                <td>
                  <input
                    type="number"
                    step="0.0001"
                    className="border rounded p-1 w-full"
                    value={linea.importe}
                    onChange={(e) => actualizarLinea(linea.key, { importe: e.target.value })}
                  />
                </td>
                <td>{ratio && linea.importe
                  ? (Number(linea.importe) * Number(ratio)).toFixed(4)
                  : "1.0000"}
                </td>
                <td>
                  <button
                    className="text-red-600"
                    onClick={() => setLineas((prev) => prev.filter((l) => l.key !== linea.key))}
                  >
                    ✕
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-sm">
          Total Debe <b>{totalDebe.toFixed(4)}</b> · Total Haber{" "}
          <b>{totalHaber.toFixed(4)}</b>
        </p>
        {desequilibrado ? (
          <p className="text-sm text-red-700 mt-1">El asiento no cuadra en divisa.</p>
        ) : (
          <p className="text-sm text-green-700 mt-1">Cuadre en divisa correcto.</p>
        )}
        {ratio && totalDebe > 0 && (
          <p className="text-sm text-slate-600 mt-1">
            Preview funcional: Debe ≈ {(totalDebe * Number(ratio)).toFixed(4)} · Haber ≈{" "}
            {(totalHaber * Number(ratio)).toFixed(4)} (una línea de redondeo 6680/7690
            absorberá el remanente).
          </p>
        )}
        <button className="mt-2 bg-slate-800 text-white rounded px-3 py-1" onClick={añadirLinea}>
          Añadir línea
        </button>
      </section>

      {aviso && <p className="mb-2 text-sm text-amber-700">{aviso}</p>}

      <button
        className="bg-blue-600 text-white rounded px-4 py-2"
        onClick={enviar}
        disabled={lineas.length < 2 || desequilibrado || lineas.some((l) => !l.cuenta_id)}
      >
        Crear asiento (POSTED)
      </button>

      {resultado && (
        <div className="mt-4 border border-green-300 rounded p-4">
          <p className="font-medium">
            Asiento {resultado.numero_asiento} creado en {resultado.divisa}
          </p>
          <p className="text-sm">
            Divisas: {resultado.importe_total_divisa} · Funcional:{" "}
            {resultado.importe_total_funcional} · Ratio {resultado.ratio} · Tipo{" "}
            {resultado.sellado ? "sellado" : "no sellado"}
          </p>
          {resultado.linea_redondeo && (
            <p className="text-sm text-amber-700">
              Línea de redondeo: cuenta {resultado.linea_redondeo.cuenta}, importe{" "}
              {resultado.linea_redondeo.importe}
            </p>
          )}
          <a className="text-sm text-blue-600 underline" href={`/asientos/${resultado.asiento_id}`}>
            Ver asiento contable
          </a>
        </div>
      )}
    </main>
  );
}