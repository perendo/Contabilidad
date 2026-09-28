"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { cambiarEstadoPlantilla, listarGenerados, obtenerPlantilla, type AccountingTemplate } from "../../../components/templates/api";

export default function PlantillaDetallePage() {
  const params = useParams<{ id: string }>();
  const [plantilla, setPlantilla] = useState<AccountingTemplate | null>(null);
  const [generados, setGenerados] = useState<Array<Record<string, unknown>>>([]);
  const [error, setError] = useState<string | null>(null);
  const cargar = useCallback(async () => { try { const [detalle, historico] = await Promise.all([obtenerPlantilla(params.id), listarGenerados(params.id)]); setPlantilla(detalle); setGenerados(historico.items); } catch (cause) { setError(cause instanceof Error ? cause.message : "No se pudo cargar"); } }, [params.id]);
  useEffect(() => { void cargar(); }, [cargar]);
  async function estado() { if (!plantilla) return; await cambiarEstadoPlantilla(plantilla.id, plantilla.estado === "activa" ? "inactivar" : "activar"); await cargar(); }
  if (error) return <main className="p-6 text-red-600">{error}</main>;
  if (!plantilla) return <main className="p-6">Cargando...</main>;
  return <main className="mx-auto max-w-5xl p-6"><Link className="text-sm text-blue-700 hover:underline" href="/plantillas">Volver</Link><div className="mt-4 flex items-center justify-between"><div><h1 className="text-2xl font-semibold">{plantilla.nombre}</h1><p className="text-sm text-gray-500">Versión {plantilla.version_actual} · {plantilla.estado}</p></div><div className="flex gap-2"><button className="rounded border px-3 py-2" type="button" onClick={() => void estado()}>{plantilla.estado === "activa" ? "Inactivar" : "Activar"}</button><Link className="rounded bg-blue-600 px-3 py-2 text-white" href={`/plantillas/${plantilla.id}/generar`}>Generar asiento</Link></div></div><section className="mt-6 rounded border bg-white p-5"><h2 className="font-semibold">Líneas</h2><ul className="mt-3 space-y-2">{plantilla.lineas.map((linea) => <li className="flex justify-between border-b py-2" key={linea.id}><span>{linea.orden}. Cuenta {linea.cuenta_id} · {linea.posicion}</span><span>{linea.importe_fijo ?? `Variable ${linea.variable_id}`}</span></li>)}</ul></section><section className="mt-6 rounded border bg-white p-5"><h2 className="font-semibold">Asientos generados</h2><ul className="mt-3 space-y-2">{generados.map((item) => <li className="border-b py-2" key={String(item.asiento_id)}>Asiento {String(item.asiento_id)} · versión {String(item.version_plantilla)} · {String(item.fecha_generacion)}</li>)}</ul>{generados.length === 0 && <p className="mt-3 text-gray-500">Todavía no hay asientos generados.</p>}</section></main>;
}
