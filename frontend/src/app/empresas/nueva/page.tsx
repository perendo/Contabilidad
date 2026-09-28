"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApiError } from "../../../components/treasury/api";
import { setEmpresaActiva } from "../../../components/treasury/empresa";
import { post } from "../../../services/client";

interface EmpresaCreada {
  company_id: number;
  nif: string;
  razon_social: string;
  role: string;
  default_company_id: number;
}

export default function NuevaEmpresaPage() {
  const router = useRouter();
  const [nif, setNif] = useState("");
  const [razonSocial, setRazonSocial] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);

  async function crear(evento: React.FormEvent) {
    evento.preventDefault();
    setError(null);
    setCargando(true);
    try {
      const creada = await post<EmpresaCreada>("/api/v1/companies", {
        nif: nif.trim(),
        razon_social: razonSocial.trim(),
      });
      setEmpresaActiva(String(creada.default_company_id));
      router.push("/remesas");
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    } finally {
      setCargando(false);
    }
  }

  return (
    <main className="p-6 max-w-md mx-auto">
      <h1 className="text-xl font-semibold mb-4">Nueva empresa</h1>
      <form onSubmit={crear} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          NIF
          <input
            required
            maxLength={20}
            value={nif}
            onChange={(e) => setNif(e.target.value)}
            className="border rounded px-3 py-1"
          />
        </label>
        <label className="flex flex-col gap-1">
          Razón social
          <input
            required
            maxLength={200}
            value={razonSocial}
            onChange={(e) => setRazonSocial(e.target.value)}
            className="border rounded px-3 py-1"
          />
        </label>
        {error && <p className="text-red-600">{error}</p>}
        <button
          type="submit"
          disabled={cargando}
          className="bg-blue-600 text-white rounded px-3 py-1 disabled:opacity-50"
        >
          {cargando ? "Creando…" : "Crear empresa"}
        </button>
      </form>
    </main>
  );
}
