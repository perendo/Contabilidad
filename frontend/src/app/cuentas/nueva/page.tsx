"use client";

import { useEffect, useState, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { crearCuenta, obtenerArbolCuentas, type CuentaNodo } from "@/services/acct/api";

export interface CuentaFormData {
  code: string;
  name: string;
  parent_id: string | null;
}

// Aplanar recursivamente el árbol de cuentas para obtener todas las cuentas padre elegibles
function aplanarCuentas(nodos: CuentaNodo[]): CuentaNodo[] {
  const resultado: CuentaNodo[] = [];
  function recorrer(lista: CuentaNodo[]) {
    for (const n of lista) {
      resultado.push(n);
      if (n.children && n.children.length > 0) {
        recorrer(n.children);
      }
    }
  }
  recorrer(nodos);
  return resultado;
}

export default function NuevaCuentaPage() {
  const searchParams = useSearchParams();
  const initialCode = searchParams ? searchParams.get("code") || "" : "";

  const [formData, setFormData] = useState<CuentaFormData>({
    code: initialCode,
    name: "",
    parent_id: null,
  });

  const [todasLasCuentas, setTodasLasCuentas] = useState<CuentaNodo[]>([]);
  const [cargandoArbol, setCargandoArbol] = useState(true);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState(false);

  // Cargar el árbol de cuentas al iniciar para tener todos los grupos, subgrupos y cuentas disponibles
  useEffect(() => {
    async function cargar() {
      try {
        setCargandoArbol(true);
        const data = await obtenerArbolCuentas();
        setTodasLasCuentas(aplanarCuentas(data.nodos || []));
      } catch (e) {
        console.error("Error al cargar cuentas para selección de padre:", e);
      } finally {
        setCargandoArbol(false);
      }
    }
    cargar();
  }, []);

  const handleCodeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const nuevoCodigo = e.target.value.replace(/[^0-9]/g, "");
    setFormData((prev) => {
      const datosActualizados = { ...prev, code: nuevoCodigo };
      // Autoseleccionar la cuenta padre correspondiente si existe en el árbol
      if (nuevoCodigo.length > 1) {
        let prefijoPadre = "";
        if (nuevoCodigo.length === 2) prefijoPadre = nuevoCodigo.slice(0, 1);
        else if (nuevoCodigo.length === 3) prefijoPadre = nuevoCodigo.slice(0, 2);
        else if (nuevoCodigo.length === 4) prefijoPadre = nuevoCodigo.slice(0, 3);
        else if (nuevoCodigo.length >= 5) prefijoPadre = nuevoCodigo.slice(0, 4);

        if (prefijoPadre) {
          const padreEncontrado = todasLasCuentas.find((c) => c.code === prefijoPadre);
          if (padreEncontrado) {
            datosActualizados.parent_id = padreEncontrado.id;
          }
        }
      }
      return datosActualizados;
    });
  };

  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({ ...formData, name: e.target.value });
  };

  // Calcular nivel esperado basado en el código
  const nivelEsperado = useMemo(() => {
    if (formData.code.length <= 4) return formData.code.length;
    if (formData.code.length >= 5 && formData.code.length <= 8) return 5;
    return 0;
  }, [formData.code]);

  // Cuentas elegibles para ser padre (nivel = nivelEsperado - 1)
  const padresElegibles = useMemo(() => {
    if (nivelEsperado <= 1) return [];
    const nivelBuscado = nivelEsperado - 1;
    return todasLasCuentas.filter((c) => c.level === nivelBuscado && c.is_active);
  }, [todasLasCuentas, nivelEsperado]);

  // Cuenta padre actualmente seleccionada
  const padreSeleccionado = useMemo(() => {
    return todasLasCuentas.find((c) => String(c.id) === String(formData.parent_id));
  }, [todasLasCuentas, formData.parent_id]);

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
      // Recargar catálogo de cuentas para refrescar el árbol
      const data = await obtenerArbolCuentas();
      setTodasLasCuentas(aplanarCuentas(data.nodos || []));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al crear la cuenta");
    } finally {
      setCargando(false);
    }
  };

  return (
    <div className="p-6 max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <svg
            aria-hidden="true"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="w-6 h-6 text-emerald-400"
          >
            <path d="M12 5v14" />
            <path d="M5 12h14" />
          </svg>
          Nueva Cuenta / Subcuenta PGC
        </h1>
        <p className="text-xs text-slate-400 mt-1">
          Alta de cuentas y subcuentas (Nivel 1 al 5) según el Plan General Contable español.
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
        <div className="p-4 bg-rose-100 text-rose-900 border border-rose-300 rounded-xl font-medium text-sm flex items-start gap-2">
          <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5 text-rose-700 shrink-0 mt-0.5">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clipRule="evenodd" />
          </svg>
          <div>
            <div className="font-bold">No se pudo crear la cuenta</div>
            <div className="text-xs mt-0.5">{error}</div>
          </div>
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
            placeholder="Ej: 170 (3 dígitos), 1700 (4 dígitos), 17001 (5 dígitos)..."
            maxLength={8}
            required
            pattern="[0-9]+"
            disabled={cargando}
          />
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-slate-600">
            <span>Solo dígitos.</span>
            {nivelEsperado > 0 && (
              <span className="font-semibold text-blue-700 bg-blue-50 px-2 py-0.5 rounded border border-blue-200">
                Nivel {nivelEsperado} {nivelEsperado >= 4 ? "· Apuntable (Subcuenta)" : "· Agrupadora (Grupo/Cuenta)"}
              </span>
            )}
          </div>
        </div>

        <div>
          <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">
            Nombre / Denominación *
          </label>
          <input
            type="text"
            value={formData.name}
            onChange={handleNameChange}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg bg-white text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-600"
            placeholder="Ej: Deudas a largo plazo con entidades de crédito, Banco Santander L/P..."
            maxLength={200}
            required
            disabled={cargando}
          />
        </div>

        <div>
          <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5 flex items-center justify-between">
            <span>Cuenta Padre {nivelEsperado > 1 ? "(Obligatoria para nivel > 1)" : "(Opcional)"}</span>
            {padreSeleccionado && (
              <span className="text-emerald-700 font-semibold font-mono text-[11px]">
                ✓ Padre: {padreSeleccionado.code} - {padreSeleccionado.name}
              </span>
            )}
          </label>

          <select
            value={formData.parent_id || ""}
            onChange={(e) => setFormData({ ...formData, parent_id: e.target.value || null })}
            disabled={cargando || cargandoArbol}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg bg-white text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-600 font-medium disabled:bg-slate-100"
          >
            <option value="">
              {nivelEsperado > 1
                ? `-- Selecciona la cuenta padre (Nivel ${nivelEsperado - 1}) --`
                : "-- Sin cuenta padre (Nivel 1 - Grupo) --"}
            </option>
            {padresElegibles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.code} — {p.name} (Nivel {p.level})
              </option>
            ))}
          </select>

          <p className="mt-1 text-xs text-slate-500">
            {nivelEsperado > 1 ? (
              padresElegibles.length > 0 ? (
                <span>El sistema autoselecciona o te permite elegir la cuenta de nivel {nivelEsperado - 1} de la que depende.</span>
              ) : (
                <span className="text-amber-700 font-medium">
                  ⚠️ No existe en el PGC la cuenta de nivel {nivelEsperado - 1} para colgar este código. Crea primero la cuenta madre.
                </span>
              )
            ) : (
              <span>Las cuentas de 1 dígito (Nivel 1) no tienen cuenta padre.</span>
            )}
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
        <h3 className="font-semibold text-xs text-white uppercase tracking-wider">Reglas de Jerarquía del PGC</h3>
        <ul className="text-xs text-slate-400 space-y-1">
          <li>• <strong>Nivel 1 (1 dígito)</strong>: Grupos principales (ej. <code>1</code> Financiación Básica). Sin padre.</li>
          <li>• <strong>Nivel 2 (2 dígitos)</strong>: Subgrupos (ej. <code>17</code> Deudas a L/P). Padre: grupo de 1 dígito.</li>
          <li>• <strong>Nivel 3 (3 dígitos)</strong>: Cuentas (ej. <code>170</code> Deudas con entidades de crédito). Padre: subgrupo de 2 dígitos (ej. <code>17</code>).</li>
          <li>• <strong>Nivel 4 (4 dígitos)</strong>: Subcuentas apuntables (ej. <code>1700</code>). Padre: cuenta de 3 dígitos (ej. <code>170</code>).</li>
          <li>• <strong>Nivel 5 (5 a 8 dígitos)</strong>: Auxiliares apuntables (ej. <code>17001</code>). Padre: subcuenta de 4 dígitos (ej. <code>1700</code>).</li>
        </ul>
      </div>
    </div>
  );
}
