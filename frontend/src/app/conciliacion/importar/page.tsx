"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApiError } from "../../../components/treasury/api";
import { cabecerasEmpresa } from "../../../components/treasury/empresa";
import { getToken } from "../../../services/client";

export default function ImportarExtractoPage() {
  const router = useRouter();
  const [archivo, setArchivo] = useState<File | null>(null);
  const [cuenta, setCuenta] = useState("");
  const [layout, setLayout] = useState("norma_43_1919");
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);

  async function subir(evento: React.FormEvent) {
    evento.preventDefault();
    if (!archivo) return;
    setError(null);
    setCargando(true);
    try {
      const datos = new FormData();
      datos.append("file", archivo);
      datos.append("layout", layout);
      if (cuenta) datos.append("cuenta", cuenta);
      const cabeceras: Record<string, string> = { ...cabecerasEmpresa() };
      const token = getToken();
      if (token) cabeceras["Authorization"] = `Bearer ${token}`;
      const respuesta = await fetch("/api/v1/extractos", { method: "POST", headers: cabeceras, body: datos });
      const cuerpo = await respuesta.json().catch(() => ({}));
      if (!respuesta.ok) {
        const detalle = (cuerpo as { detail?: unknown })?.detail;
        const msg = typeof detalle === "string" ? detalle : (detalle as { detail?: string })?.detail;
        throw new ApiError(respuesta.status, msg ?? "Error al importar");
      }
      setPreview(
        `Importado: ${cuerpo.n_movimientos} movimientos, saldo final ${cuerpo.saldo_final}`
      );
      router.push("/conciliacion");
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    } finally {
      setCargando(false);
    }
  }

  return (
    <main className="p-6 max-w-lg mx-auto">
      <h1 className="text-xl font-semibold mb-4">Importar extracto bancario</h1>
      <form onSubmit={subir} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          Fichero (norma 43/19 o CSV)
          <input
            type="file"
            accept=".txt,.csv"
            onChange={(e) => setArchivo(e.target.files?.[0] ?? null)}
          />
        </label>
        <label className="flex flex-col gap-1">
          Cuenta 572 (código)
          <input value={cuenta} onChange={(e) => setCuenta(e.target.value)} className="border rounded px-3 py-1" placeholder="5720" />
        </label>
        <label className="flex flex-col gap-1">
          Layout
          <select value={layout} onChange={(e) => setLayout(e.target.value)} className="border rounded px-2 py-1">
            <option value="norma_43_1919">Norma 43/19</option>
            <option value="csv_normalizado">CSV normalizado</option>
          </select>
        </label>
        {error && <p className="text-red-600">{error}</p>}
        {preview && <p className="text-emerald-700">{preview}</p>}
        <button type="submit" disabled={cargando || !archivo} className="bg-blue-600 text-white rounded px-3 py-1 disabled:opacity-50">
          {cargando ? "Importando…" : "Importar"}
        </button>
      </form>
    </main>
  );
}
