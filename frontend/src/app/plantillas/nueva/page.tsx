"use client";

import Link from "next/link";
import { useState } from "react";

import TemplateEditor from "../../../components/templates/TemplateEditor";

export default function NuevaPlantillaPage() {
  const [creada, setCreada] = useState<string | null>(null);

  return (
    <main className="mx-auto max-w-4xl p-6">
      <Link className="text-sm text-blue-700 hover:underline" href="/plantillas">Volver a plantillas</Link>
      <h1 className="mt-4 text-2xl font-semibold">Nueva plantilla</h1>
      {creada ? (
        <p className="mt-6 rounded border bg-white p-6 text-emerald-700">
          Plantilla creada.{" "}
          <Link className="underline" href={`/plantillas/${creada}`}>Abrir detalle</Link>
        </p>
      ) : (
        <div className="mt-6">
          <TemplateEditor onCreada={setCreada} />
        </div>
      )}
    </main>
  );
}
