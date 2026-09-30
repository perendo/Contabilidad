"use client";

import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { crearCuenta, sugerirCuentas, type CuentaSugerida } from "@/services/acct/api";
import { AccountAutocomplete } from "@/components/acct/AccountAutocomplete";

export interface CuentaFormData {
  code: string;
  name: string;
  parent_id: string | null;
}

export default function NuevaCuentaPage() {
  const searchParams = useSearchParams();
  const initialCode = searchParams ? searchParams.get("code") || "" : "";

  const [formData, setFormData] = useState<CuentaFormData>({
    code: initialCode,
    name: "",
    parent_id: null,
  });

  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState(false);
  const [sugerenciasPadre, setSugerenciasPadre] = useState<CuentaSugerida[]>([]);
  const debouncePadre = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (debouncePadre.current) clearTimeout(debouncePadre.current);
    };
  }, []);

  const handleCodeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({ ...formData, code: e.target.value });
  };

  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({ ...formData, name: e.target.value });
  };

  const handlePadreSeleccionado = (cuenta: CuentaSugerida | null) => {
    setFormData({ ...formData, parent_id: cuenta?.id || null });
    setSugerenciasPadre([]);
  };

  const handleBuscarPadre = (query: string) => {
    if (debouncePadre.current) clearTimeout(debouncePadre.current);
    if (query.length < 1) {
      setSugerenciasPadre([]);
      return;
    }
    debouncePadre.current = setTimeout(async () => {
      try {
        const data = await sugerirCuentas(query, 20);
        // Filtrar solo cuentas que NO son hojas (nivel < 4) para poder ser madres
        setSugerenciasPadre(data.items.filter((c) => c.level < 4));
      } catch {
        setSugerenciasPadre([]);
      }
    }, 250);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setExito(false);
    setCargando(true);
    try {
      await crearCuenta({
        code: formData.code,
        name: formData.name,
        parent_id: formData.parent_id || undefined,
      });
      setExito(true);
      setFormData({ code: "", name: "", parent_id: null });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al crear la cuenta");
    } finally {
      setCargando(false);
    }
  };

  // Calcular nivel esperado basado en el código
  const nivelEsperado =
    formData.code.length <= 4
      ? formData.code.length
      : formData.code.length >= 5 && formData.code.length <= 8
      ? 5
      : 0;

  return (
    <div className="p-6 max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-6 h-6 text-emerald-400">
            <path d="M12 5v14" />
            <path d="M5 12h14" />
          </svg>
          Nueva Cuenta / Subcuenta PGC
        </h1>
        <p className="text-xs text-slate-400 mt-1">
          Alta de cuentas y subcuentas apuntables (ej. Grupo 17, 40, 41, 43, 57) según el Plan General Contable.
        </p>
      </div>

      {exito && (
        <div className="p-4 bg-emerald-100 text-emerald-900 border border-emerald-300 rounded-xl font-medium text-sm flex items-center gap-2">
          <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5 text-emerald-700 shrink-0">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clipRule="evenodd" />
          </svg>
          <span>Cuenta creada correctamente en el Plan General Contable. Ya está disponible para asentar.</span>
        </div>
      )}

      {error && (
        <div className="p-4 bg-rose-100 text-rose-900 border border-rose-300 rounded-xl font-medium text-sm flex items-center gap-2">
          <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5 text-rose-700 shrink-0">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clipRule="evenodd" />
          </svg>
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4 bg-white p-6 rounded-xl shadow-lg border border-slate-300 text-slate-900">
        <div>
          <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">
            Código Contable *
          </label>
          <input
            type="text"
            value={formData.code}
            onChange={handleCodeChange}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg bg-white text-slate-900 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-600"
            placeholder="Ej: 17000001, 17300001, 40000010..."
            maxLength={8}
            required
            pattern="[0-9]+"
            disabled={cargando}
          />
          <p className="mt-1 text-xs text-slate-500">
            Solo dígitos. Nivel 1-4: longitud = nivel (ej. 4 dígitos para subcuentas). Nivel 5: 5-8 dígitos.
            {nivelEsperado > 0 && (
              <span className="ml-2 font-bold text-blue-700">Nivel estimado: {nivelEsperado} ({nivelEsperado >= 4 ? "Apuntable" : "Cuenta de Grupo"})</span>
            )}
          </p>
        </div>

        <div>
          <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">
            Nombre / Razón Social *
          </label>
          <input
            type="text"
            value={formData.name}
            onChange={handleNameChange}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg bg-white text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-600"
            placeholder="Ej: Banco Santander L/P, Proveedor Maquinaria S.L..."
            maxLength={200}
            required
            disabled={cargando}
          />
        </div>

        <div>
          <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">
            Cuenta Padre (Opcional)
          </label>
          <AccountAutocomplete
            value={formData.parent_id ? `${formData.parent_id}` : ""}
            onChange={handlePadreSeleccionado}
            onSearch={handleBuscarPadre}
            sugerencias={sugerenciasPadre}
            placeholder="Buscar cuenta madre (ej: 170, 173, 400)..."
            disabled={cargando}
          />
          <p className="mt-1 text-xs text-slate-500">
            Niveles 1 a 3 (grupos, subgrupos, cuentas de 3 dígitos).
            {formData.parent_id && <span className="text-emerald-700 font-bold ml-2">✓ Madre seleccionada</span>}
          </p>
        </div>

        <div className="pt-4 border-t border-slate-200">
          <button
            type="submit"
            disabled={cargando}
            className="w-full py-2.5 px-4 bg-blue-600 text-white font-bold rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 shadow-sm disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {cargando ? "Guardando en PGC..." : "Dar de Alta en PGC"}
          </button>
        </div>
      </form>

      <div className="p-4 bg-slate-950 border border-slate-800 rounded-xl text-slate-300 space-y-2">
        <h3 className="font-semibold text-xs text-white uppercase tracking-wider">Reglas del Plan General Contable</h3>
        <ul className="text-xs text-slate-400 space-y-1">
          <li>• Código numérico único por empresa activa (máx. 8 dígitos).</li>
          <li>• <strong>Apuntabilidad</strong>: Solo las subcuentas de nivel ≥ 4 (4 a 8 dígitos) admiten asientos contables en el diario.</li>
          <li>• Al crear una subcuenta hija bajo una cuenta, la cuenta madre queda como cuenta sumatoria/agrupadora.</li>
        </ul>
      </div>
    </div>
  );
}
