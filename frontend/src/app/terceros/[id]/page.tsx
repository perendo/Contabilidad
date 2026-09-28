"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../../../components/treasury/api";
import { get } from "../../../services/client";

interface Subcuenta {
  tipo: string;
  cuenta_codigo: string;
}

interface Saldo {
  saldo_pendiente: string;
  n_vencimientos: number;
  subcuentas: Subcuenta[];
}

interface Tercero {
  id: string;
  nif: string | null;
  razon_social: string;
  es_cliente: boolean;
  es_proveedor: boolean;
  iban: string | null;
  banco: string | null;
  activo: boolean;
  saldo: Saldo;
}

export default function FichaTerceroPage() {
  const params = useParams<{ id: string }>();
  const [tercero, setTercero] = useState<Tercero | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    try {
      setTercero(await get<Tercero>(`/api/v1/terceros/${params.id}`));
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    }
  }, [params.id]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  return (
    <main className="p-6 max-w-3xl mx-auto">
      <h1 className="text-xl font-semibold mb-4">Ficha de tercero</h1>
      {error && <p className="text-red-600 mb-4">{error}</p>}
      {tercero && (
        <>
          <dl className="grid grid-cols-2 gap-2 mb-4 text-sm">
            <dt className="font-medium">Razón social</dt>
            <dd>{tercero.razon_social}</dd>
            <dt className="font-medium">NIF</dt>
            <dd className="font-mono">{tercero.nif}</dd>
            <dt className="font-medium">Rol</dt>
            <dd>
              {[tercero.es_cliente && "Cliente", tercero.es_proveedor && "Proveedor"]
                .filter(Boolean)
                .join(" / ")}
            </dd>
            <dt className="font-medium">IBAN</dt>
            <dd className="font-mono">{tercero.iban ?? "—"}</dd>
            <dt className="font-medium">Estado</dt>
            <dd>{tercero.activo ? "Activo" : "Inactivo"}</dd>
            <dt className="font-medium">Saldo pendiente</dt>
            <dd className="font-mono">{tercero.saldo.saldo_pendiente}</dd>
          </dl>
          <h2 className="font-semibold mb-2">Subcuentas</h2>
          <ul className="mb-4 text-sm">
            {tercero.saldo.subcuentas.map((s) => (
              <li key={s.tipo} className="font-mono">
                {s.tipo}: {s.cuenta_codigo}
              </li>
            ))}
          </ul>
          <Link href="/terceros" className="text-blue-700 underline">
            Volver al listado
          </Link>
        </>
      )}
    </main>
  );
}
