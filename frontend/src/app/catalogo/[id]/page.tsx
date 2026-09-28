"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  activarVersion,
  obtenerVersion,
  versionVigente,
  type EstadoCuenta,
  type VersionDetalle,
  type VersionResumen,
} from "@/components/catalog/api";

const CLASES_ESTADO: Record<EstadoCuenta, string> = {
  igual: "bg-gray-100 text-gray-600",
  nueva: "bg-emerald-100 text-emerald-800",
  renombrada: "bg-blue-100 text-blue-800",
  suprimida: "bg-red-100 text-red-800",
};

export default function DetalleCatalogoPage() {
  const params = useParams<{ id: string }>();
  const versionId = params.id;
  const [detalle, setDetalle] = useState<VersionDetalle | null>(null);
  const [codigosOrigen, setCodigosOrigen] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);

  const [filtroEstado, setFiltroEstado] = useState("");
  const [busqueda, setBusqueda] = useState("");

  const [fechaConsulta, setFechaConsulta] = useState("");
  const [vigente, setVigente] = useState<VersionResumen | null>(null);

  const recargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const datos = await obtenerVersion(versionId);
      setDetalle(datos);
      const mapeoConOrigen = datos.mapeos.find(
        (m) => m.cuenta_origen_id && m.version_origen_id !== datos.id
      );
      if (mapeoConOrigen) {
        try {
          const origen = await obtenerVersion(mapeoConOrigen.version_origen_id);
          const mapa: Record<string, string> = {};
          for (const cuenta of origen.cuentas) mapa[cuenta.id] = cuenta.codigo_version;
          setCodigosOrigen(mapa);
        } catch {
          setCodigosOrigen({});
        }
      } else {
        setCodigosOrigen({});
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error de conexión");
    } finally {
      setCargando(false);
    }
  }, [versionId]);

  useEffect(() => {
    void recargar();
  }, [recargar]);

  async function activar() {
    if (!detalle) return;
    const ok = window.confirm(
      `¿Activar la versión "${detalle.codigo}"?\n` +
        "Pasará a vigente y quedará bloqueada su modificación."
    );
    if (!ok) return;
    setAviso(null);
    setError(null);
    try {
      await activarVersion(detalle.id);
      setAviso("Versión activada.");
      await recargar();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Error de conexión");
    }
  }

  async function consultarVigente() {
    if (!fechaConsulta) return;
    setAviso(null);
    setError(null);
    try {
      setVigente(await versionVigente(fechaConsulta));
    } catch (e) {
      setVigente(null);
      setError(e instanceof ApiError ? e.message : "Error de conexión");
    }
  }

  const cuentasFiltradas = useMemo(() => {
    if (!detalle) return [];
    const texto = busqueda.trim().toLowerCase();
    return detalle.cuentas.filter((cuenta) => {
      if (filtroEstado && cuenta.estado !== filtroEstado) return false;
      if (
        texto &&
        !cuenta.codigo_version.toLowerCase().includes(texto) &&
        !cuenta.nombre_version.toLowerCase().includes(texto)
      ) {
        return false;
      }
      return true;
    });
  }, [detalle, filtroEstado, busqueda]);

  const cuentasPorId = useMemo(() => {
    const mapa: Record<string, string> = {};
    for (const cuenta of detalle?.cuentas ?? []) mapa[cuenta.id] = cuenta.codigo_version;
    return mapa;
  }, [detalle]);

  if (cargando) {
    return (
      <main className="p-6 max-w-5xl mx-auto text-sm text-gray-500">Cargando…</main>
    );
  }
  if (!detalle) {
    return (
      <main className="p-6 max-w-5xl mx-auto space-y-3">
        <p className="text-sm text-red-600">{error ?? "Versión no encontrada"}</p>
        <Link className="text-blue-600 underline" href="/catalogo">
          Volver al catálogo
        </Link>
      </main>
    );
  }

  return (
    <main className="p-6 max-w-5xl mx-auto space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">
            {detalle.codigo}{" "}
            <span className="text-base text-gray-500">
              (v{detalle.numero_version})
            </span>
          </h1>
          <p className="text-sm text-gray-600">
            Vigencia: {detalle.fecha_inicio} → {detalle.fecha_fin ?? "…"} ·{" "}
            {detalle.estado}
            {detalle.es_migracion ? " · importada" : ""}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {detalle.estado === "borrador" && (
            <button
              type="button"
              onClick={() => void activar()}
              className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700"
            >
              Activar versión
            </button>
          )}
          <Link className="text-sm text-blue-600 underline" href="/catalogo">
            Volver
          </Link>
        </div>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}
      {aviso && <p className="text-sm text-emerald-700">{aviso}</p>}

      <section className="rounded border p-4 space-y-2">
        <h2 className="font-medium">Cuenta vigente en fecha</h2>
        <div className="flex items-center gap-2">
          <input
            type="date"
            className="border rounded px-2 py-1 text-sm"
            value={fechaConsulta}
            onChange={(evento) => setFechaConsulta(evento.target.value)}
          />
          <button
            type="button"
            onClick={() => void consultarVigente()}
            className="rounded border px-3 py-1 text-sm hover:bg-gray-50"
          >
            Consultar
          </button>
        </div>
        {vigente && (
          <p className="text-sm">
            Versión <span className="font-mono">{vigente.codigo}</span> (v
            {vigente.numero_version}) — resolución:{" "}
            <span className="font-medium">{vigente.resolucion}</span>
          </p>
        )}
      </section>

      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="font-medium">
            Cuentas ({cuentasFiltradas.length}/{detalle.cuentas.length})
          </h2>
          <div className="flex items-center gap-2">
            <input
              type="search"
              placeholder="Buscar código o nombre"
              className="border rounded px-2 py-1 text-sm"
              value={busqueda}
              onChange={(evento) => setBusqueda(evento.target.value)}
            />
            <select
              className="border rounded px-2 py-1 text-sm"
              value={filtroEstado}
              onChange={(evento) => setFiltroEstado(evento.target.value)}
            >
              <option value="">Todos los estados</option>
              <option value="igual">Igual</option>
              <option value="nueva">Nueva</option>
              <option value="renombrada">Renombrada</option>
              <option value="suprimida">Suprimida</option>
            </select>
          </div>
        </div>
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b text-left text-gray-500">
              <th className="py-2 pr-3">Código</th>
              <th className="py-2 pr-3">Nombre</th>
              <th className="py-2">Estado</th>
            </tr>
          </thead>
          <tbody>
            {cuentasFiltradas.map((cuenta) => (
              <tr key={cuenta.id} className="border-b">
                <td className="py-1.5 pr-3 font-mono">{cuenta.codigo_version}</td>
                <td className="py-1.5 pr-3">{cuenta.nombre_version}</td>
                <td className="py-1.5">
                  <span
                    className={`rounded px-2 py-0.5 text-xs ${CLASES_ESTADO[cuenta.estado]}`}
                  >
                    {cuenta.estado}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="space-y-2">
        <h2 className="font-medium">Mapeos ({detalle.mapeos.length})</h2>
        {detalle.mapeos.length === 0 ? (
          <p className="text-sm text-gray-500">Sin mapeos registrados.</p>
        ) : (
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b text-left text-gray-500">
                <th className="py-2 pr-3">Origen</th>
                <th className="py-2 pr-3">Destino</th>
                <th className="py-2 pr-3">Tipo</th>
                <th className="py-2 pr-3">Requiere reclasificación</th>
                <th className="py-2">Origen del mapeo</th>
              </tr>
            </thead>
            <tbody>
              {detalle.mapeos
                .filter((mapeo) => mapeo.tipo_movimiento !== "igual")
                .map((mapeo) => (
                  <tr key={mapeo.id} className="border-b">
                    <td className="py-1.5 pr-3 font-mono">
                      {mapeo.cuenta_origen_id
                        ? (codigosOrigen[mapeo.cuenta_origen_id] ?? "—")
                        : "—"}
                    </td>
                    <td className="py-1.5 pr-3 font-mono">
                      {mapeo.cuenta_destino_id
                        ? (cuentasPorId[mapeo.cuenta_destino_id] ?? "—")
                        : "—"}
                    </td>
                    <td className="py-1.5 pr-3">{mapeo.tipo_movimiento}</td>
                    <td className="py-1.5 pr-3">
                      {mapeo.requiere_reclasificacion ? "sí" : "no"}
                    </td>
                    <td className="py-1.5">{mapeo.origen}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
