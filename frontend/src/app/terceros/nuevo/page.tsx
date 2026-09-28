"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApiError } from "../../../components/treasury/api";
import { post } from "../../../services/client";

export default function NuevoTerceroPage() {
  const router = useRouter();
  const [nif, setNif] = useState("");
  const [razonSocial, setRazonSocial] = useState("");
  const [esCliente, setEsCliente] = useState(true);
  const [esProveedor, setEsProveedor] = useState(false);
  const [iban, setIban] = useState("");
  const [banco, setBanco] = useState("");
  const [telefono, setTelefono] = useState("");
  const [correo, setCorreo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);

  async function crear(evento: React.FormEvent) {
    evento.preventDefault();
    setError(null);
    setCargando(true);
    try {
      const creado = await post<{ id: string }>("/api/v1/terceros", {
        nif,
        razon_social: razonSocial,
        es_cliente: esCliente,
        es_proveedor: esProveedor,
        iban: iban || null,
        banco: banco || null,
        telefono: telefono || null,
        correo: correo || null,
      });
      router.push(`/terceros/${creado.id}`);
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Error de conexión");
    } finally {
      setCargando(false);
    }
  }

  return (
    <main className="p-6 max-w-lg mx-auto">
      <h1 className="text-xl font-semibold mb-4">Nuevo tercero</h1>
      <form onSubmit={crear} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          NIF
          <input required maxLength={20} value={nif} onChange={(e) => setNif(e.target.value)} className="border rounded px-3 py-1" />
        </label>
        <label className="flex flex-col gap-1">
          Razón social
          <input required maxLength={200} value={razonSocial} onChange={(e) => setRazonSocial(e.target.value)} className="border rounded px-3 py-1" />
        </label>
        <div className="flex gap-4">
          <label className="flex gap-2 items-center">
            <input type="checkbox" checked={esCliente} onChange={(e) => setEsCliente(e.target.checked)} />
            Cliente
          </label>
          <label className="flex gap-2 items-center">
            <input type="checkbox" checked={esProveedor} onChange={(e) => setEsProveedor(e.target.checked)} />
            Proveedor
          </label>
        </div>
        <label className="flex flex-col gap-1">
          IBAN (opcional)
          <input value={iban} onChange={(e) => setIban(e.target.value)} className="border rounded px-3 py-1" />
        </label>
        <label className="flex flex-col gap-1">
          Banco
          <input value={banco} onChange={(e) => setBanco(e.target.value)} className="border rounded px-3 py-1" />
        </label>
        <label className="flex flex-col gap-1">
          Teléfono
          <input value={telefono} onChange={(e) => setTelefono(e.target.value)} className="border rounded px-3 py-1" />
        </label>
        <label className="flex flex-col gap-1">
          Correo
          <input type="email" value={correo} onChange={(e) => setCorreo(e.target.value)} className="border rounded px-3 py-1" />
        </label>
        {error && <p className="text-red-600">{error}</p>}
        <button type="submit" disabled={cargando} className="bg-blue-600 text-white rounded px-3 py-1 disabled:opacity-50">
          {cargando ? "Creando…" : "Crear tercero"}
        </button>
      </form>
    </main>
  );
}
