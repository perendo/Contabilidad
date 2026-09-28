"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { listarPlantillas, type AccountingTemplate } from "../../components/templates/api";
import { ApiError } from "../../components/treasury/api";

export default function PlantillasPage() {
  const [items, setItems] = useState<AccountingTemplate[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void listarPlantillas().then((data) => setItems(data.items)).catch((cause) => {
      setError(cause instanceof ApiError ? cause.message : "No se pudieron cargar las plantillas");
    });
  }, []);

  return (
    <main className="mx-auto max-w-6xl p-6">
      <div className="mb-6 flex items-center justify-between">
        <div><p className="text-sm text-gray-500">Contabilidad</p><h1 className="text-2xl font-semibold">Plantillas de asientos</h1></div>
        <Link className="rounded bg-blue-600 px-4 py-2 text-white" href="/plantillas/nueva">Nueva plantilla</Link>
      </div>
      {error && <p className="mb-4 text-red-600">{error}</p>}
      <div className="overflow-hidden rounded border bg-white">
        <table className="w-full text-left text-sm"><thead className="bg-gray-50"><tr><th className="p-3">Nombre</th><th className="p-3">Categoría</th><th className="p-3">Versión</th><th className="p-3">Estado</th><th className="p-3" /></tr></thead>
          <tbody>{items.map((item) => <tr className="border-t" key={item.id}><td className="p-3 font-medium">{item.nombre}</td><td className="p-3">{item.categoria ?? "-"}</td><td className="p-3">{item.version_actual}</td><td className="p-3">{item.estado}</td><td className="p-3 text-right"><Link className="text-blue-700 hover:underline" href={`/plantillas/${item.id}`}>Abrir</Link></td></tr>)}</tbody>
        </table>
        {items.length === 0 && <p className="p-6 text-gray-500">No hay plantillas para esta empresa.</p>}
      </div>
    </main>
  );
}
