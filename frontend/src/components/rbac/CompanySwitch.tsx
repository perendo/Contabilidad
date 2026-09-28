"use client";

import { useEffect, useState } from "react";

import { getEmpresaActiva, setEmpresaActiva, suscribirEmpresa } from "../treasury/empresa";
import { get, post } from "@/services/client";

interface EmpresaAccesible {
  company_id: number;
  razon_social: string;
  role: string;
}

interface Sesion {
  companies: EmpresaAccesible[];
}

export default function CompanySwitch() {
  const [empresas, setEmpresas] = useState<EmpresaAccesible[]>([]);
  const [activa, setActiva] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<Sesion>("/api/v1/auth/me")
      .then((sesion) => {
        setEmpresas(sesion.companies);
        setActiva(getEmpresaActiva());
      })
      .catch(() => setEmpresas([]));
    return suscribirEmpresa(setActiva);
  }, []);

  async function cambiar(empresaId: string) {
    if (!empresaId) return;
    setError(null);
    try {
      await post("/api/v1/auth/switch-company", {
        company_id: Number(empresaId),
      });
      setEmpresaActiva(empresaId);
    } catch {
      setError("Sin acceso a la empresa solicitada");
      setActiva(getEmpresaActiva());
    }
  }

  return (
    <div className="border-b bg-slate-50 px-6 py-2 flex items-center gap-2 text-sm">
      <span className="font-medium">Empresa:</span>
      <select
        className="border rounded px-2 py-1"
        value={activa ?? ""}
        onChange={(evento) => cambiar(evento.target.value)}
      >
        <option value="">Seleccionar…</option>
        {empresas.map((empresa) => (
          <option key={empresa.company_id} value={String(empresa.company_id)}>
            {empresa.razon_social} ({empresa.role})
          </option>
        ))}
      </select>
      {error && <span className="text-red-600">{error}</span>}
    </div>
  );
}
