"use client";

import { useParams } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";

import CuentaPicker from "../../../../components/ngo/CuentaPicker";
import {
  ApiError,
  aprobarArqueo,
  archivarArqueo,
  formatearImporte,
  inactivarCaja,
  listarArqueos,
  obtenerCaja,
  realizarArqueo,
  registrarMovimiento,
  type Arqueo,
  type DetalleCaja,
  type Movimiento,
} from "../../../../components/ngo/api";
import type { CuentaSugerida } from "../../../../services/acct/api";

export default function CajaDetallePage() {
  const params = useParams<{ id: string }>();
  const cajaId = params.id;

  const [caja, setCaja] = useState<DetalleCaja | null>(null);
  const [arqueos, setArqueos] = useState<Arqueo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [mensaje, setMensaje] = useState<string | null>(null);

  const [tipo, setTipo] = useState<"entrada" | "salida">("entrada");
  const [importe, setImporte] = useState("");
  const [fecha, setFecha] = useState(new Date().toISOString().slice(0, 10));
  const [concepto, setConcepto] = useState("");
  const [contrapartida, setContrapartida] = useState<CuentaSugerida | null>(null);

  const [fechaArqueo, setFechaArqueo] = useState(new Date().toISOString().slice(0, 10));
  const [efectivo, setEfectivo] = useState("");
  const [detalleArqueo, setDetalleArqueo] = useState("");
  const [idAjuste, setIdAjuste] = useState("");

  const cargar = useCallback(async () => {
    setError(null);
    try {
      const [c, arq] = await Promise.all([obtenerCaja(cajaId), listarArqueos({ caja_id: cajaId })]);
      setCaja(c);
      setArqueos(arq.items);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    }
  }, [cajaId]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  async function alMovimiento(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!contrapartida) {
      setError("Selecciona la cuenta contrapartida");
      return;
    }
    try {
      await registrarMovimiento(cajaId, {
        tipo,
        importe,
        fecha,
        concepto,
        contrapartida_cuenta_id: Number(contrapartida.id),
      });
      setImporte("");
      setConcepto("");
      setContrapartida(null);
      setMensaje("Movimiento registrado");
      cargar();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Error de conexión");
    }
  }

  async function alArqueo(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const arqueo = await realizarArqueo(cajaId, {
        fecha: fechaArqueo,
        efectivo_contado: efectivo,
        detalle: detalleArqueo || null,
      });
      setMensaje(
        arqueo.estado === "cuadra"
          ? "Arqueo cuadra y queda aprobado"
          : `Diferencia de ${arqueo.diferencia} € — pendiente de aprobar`
      );
      setEfectivo("");
      cargar();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Error de conexión");
    }
  }

  async function alAprobar(arqueo: Arqueo) {
    setError(null);
    try {
      await aprobarArqueo(arqueo.id, idAjuste || null);
      setIdAjuste("");
      setMensaje("Arqueo aprobado");
      cargar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }

  async function alArchivar(arqueo: Arqueo) {
    setError(null);
    try {
      await archivarArqueo(arqueo.id);
      setMensaje("Arqueo archivado");
      cargar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }

  async function alInactivar() {
    setError(null);
    try {
      await inactivarCaja(cajaId);
      setMensaje("Caja inactivada");
      cargar();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
    }
  }

  if (!caja) {
    return (
      <main className="p-6 max-w-5xl mx-auto">
        <h1 className="text-xl font-semibold mb-4">Caja</h1>
        {error && <p className="text-red-600">{error}</p>}
        <p className="text-gray-500">Cargando…</p>
      </main>
    );
  }

  return (
    <main className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">{caja.nombre}</h1>
        {caja.estado === "activa" && (
          <button
            onClick={alInactivar}
            className="bg-red-600 text-white rounded px-4 py-2"
          >
            Inactivar
          </button>
        )}
      </div>
      <p className="text-gray-600 text-sm mb-4">
        {caja.tipo} · Cuenta 570 #{caja.cuenta_570_id} · {caja.estado} · Saldo{" "}
        <span className="font-mono">{formatearImporte(caja.saldo)}</span>
      </p>

      {mensaje && <p className="text-green-700 mb-4">{mensaje}</p>}
      {error && <p className="text-red-600 mb-4">{error}</p>}

      <div className="grid grid-cols-2 gap-4 mb-6">
        <form
          onSubmit={alMovimiento}
          className="border rounded p-4 bg-gray-50 space-y-3"
        >
          <h2 className="text-lg font-semibold">Registrar movimiento</h2>
          <div className="flex items-center gap-3">
            <select
              value={tipo}
              onChange={(e) => setTipo(e.target.value as "entrada" | "salida")}
              disabled={caja.estado === "inactiva"}
              className="border rounded px-3 py-2"
            >
              <option value="entrada">Entrada</option>
              <option value="salida">Salida</option>
            </select>
            <input
              value={importe}
              onChange={(e) => setImporte(e.target.value)}
              placeholder="Importe"
              type="number"
              step="0.0001"
              min="0"
              required
              className="border rounded px-3 py-2 w-32"
            />
            <input
              value={fecha}
              onChange={(e) => setFecha(e.target.value)}
              type="date"
              required
              className="border rounded px-3 py-2"
            />
          </div>
          <input
            value={concepto}
            onChange={(e) => setConcepto(e.target.value)}
            placeholder="Concepto"
            required
            className="border rounded px-3 py-2 w-full"
          />
          <div>
            <label className="text-sm text-gray-600 block mb-1">
              Contrapartida
            </label>
            <CuentaPicker valor="" alCambiar={setContrapartida} />
          </div>
          <button
            type="submit"
            disabled={caja.estado === "inactiva"}
            className="bg-blue-600 text-white rounded px-4 py-2"
          >
            Registrar
          </button>
        </form>

        <form
          onSubmit={alArqueo}
          className="border rounded p-4 bg-gray-50 space-y-3"
        >
          <h2 className="text-lg font-semibold">Realizar arqueo</h2>
          <div className="flex items-center gap-3">
            <input
              value={fechaArqueo}
              onChange={(e) => setFechaArqueo(e.target.value)}
              type="date"
              required
              className="border rounded px-3 py-2"
            />
            <input
              value={efectivo}
              onChange={(e) => setEfectivo(e.target.value)}
              placeholder="Efectivo contado"
              type="number"
              step="0.0001"
              min="0"
              required
              className="border rounded px-3 py-2 w-40"
            />
          </div>
          <input
            value={detalleArqueo}
            onChange={(e) => setDetalleArqueo(e.target.value)}
            placeholder="Detalle de la diferencia (opcional)"
            className="border rounded px-3 py-2 w-full"
          />
          <button
            type="submit"
            className="bg-green-600 text-white rounded px-4 py-2"
          >
            Realizar arqueo
          </button>
        </form>
      </div>

      <h2 className="text-lg font-semibold mb-2">Movimientos</h2>
      <table className="w-full text-sm border rounded mb-6">
        <thead>
          <tr className="text-left bg-gray-100">
            <th className="p-2">Fecha</th>
            <th className="p-2">Tipo</th>
            <th className="p-2">Importe</th>
            <th className="p-2">Asiento</th>
          </tr>
        </thead>
        <tbody>
          {(caja.movimientos.items ?? []).map((m: Movimiento) => (
            <tr key={m.id} className="border-t">
              <td className="p-2">{m.fecha}</td>
              <td className="p-2">{m.tipo}</td>
              <td className="p-2 font-mono">{formatearImporte(m.importe)}</td>
              <td className="p-2 font-mono">
                <a
                  className="text-blue-600 underline"
                  href={`/contabilidad/asientos/${m.asiento_id}`}
                >
                  {m.asiento_id.slice(0, 8)}
                </a>
              </td>
            </tr>
          ))}
          {(caja.movimientos.items ?? []).length === 0 && (
            <tr>
              <td colSpan={4} className="p-2 text-gray-500">
                Sin movimientos
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <h2 className="text-lg font-semibold mb-2">Arqueos</h2>
      <table className="w-full text-sm border rounded">
        <thead>
          <tr className="text-left bg-gray-100">
            <th className="p-2">Fecha</th>
            <th className="p-2">Saldo libros</th>
            <th className="p-2">Efectivo</th>
            <th className="p-2">Diferencia</th>
            <th className="p-2">Estado</th>
            <th className="p-2"></th>
          </tr>
        </thead>
        <tbody>
          {arqueos.map((a) => (
            <tr key={a.id} className="border-t">
              <td className="p-2">{a.fecha}</td>
              <td className="p-2 font-mono">{formatearImporte(a.saldo_libros)}</td>
              <td className="p-2 font-mono">{formatearImporte(a.efectivo_contado)}</td>
              <td className="p-2 font-mono">{formatearImporte(a.diferencia)}</td>
              <td className="p-2">
                {a.estado}
                {a.archivado ? " · archivado" : ""}
              </td>
              <td className="p-2">
                {a.estado === "con_diferencia" && !a.archivado && (
                  <div className="flex items-center gap-2">
                    <input
                      value={idAjuste}
                      onChange={(e) => setIdAjuste(e.target.value)}
                      placeholder="Asiento de ajuste (UUID)"
                      className="border rounded px-2 py-1 text-xs w-44"
                    />
                    <button
                      onClick={() => alAprobar(a)}
                      className="bg-blue-600 text-white rounded px-2 py-1 text-xs"
                    >
                      Aprobar
                    </button>
                    <button
                      onClick={() => alArchivar(a)}
                      className="text-red-600 underline text-xs"
                    >
                      Archivar
                    </button>
                  </div>
                )}
              </td>
            </tr>
          ))}
          {arqueos.length === 0 && (
            <tr>
              <td colSpan={6} className="p-2 text-gray-500">
                Sin arqueos
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </main>
  );
}