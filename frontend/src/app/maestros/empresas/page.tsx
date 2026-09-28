"use client";

/**
 * LISTADO DE EMPRESAS (SPEC-031, US5, T052, FR-028)
 *
 * El listado de empresas del ámbito del usuario. Se pidió en la superficie de Maestros
 * porque es el único sitio donde "empresa" es un dato maestro y no el contexto de
 * trabajo: en el resto de pantallas la empresa es la cabecera `X-Empresa-Activa` y no
 * tiene una pantalla propia.
 *
 * De dónde salen los datos
 * ------------------------
 *
 * De `GET /api/v1/companies`, que ya existía de SPEC-003. No se ha creado endpoint
 * nuevo: el listado de empresas del usuario es exactamente lo que ese endpoint ya
 * responde, y duplicarlo en la API de navegación sería una segunda fuente de verdad
 * sobre qué empresas ve un usuario.
 *
 * La lista de la zona de contexto y la de esta pantalla salen del mismo sitio, y eso es
 * deliberado: si un cambio de permisos de empresa hiciera que una mostrara una empresa y la
 * otra no, el usuario vería empresas que puede tener y no puede elegir, o al revés. Ver
 * `ContextZone`, que la carga por el mismo motivo.
 *
 * Clicar una fila cambia la empresa activa, que es lo mismo que hacer la zona de
 * contexto. Se reutiliza `cambiarEmpresa` del `SessionContext` para que las dos rutas
 * dejen el mismo estado, incluida la cabecera de ejercicio.
 */

import { useCallback, useEffect, useState } from "react";

import { get } from "@/services/client";
import { useSesion } from "@/components/navigation/SessionContext";

interface Empresa {
  company_id: number;
  razon_social: string;
  nif?: string | null;
  is_active?: boolean;
}

export default function MaestrosEmpresasPage() {
  const { contexto, cambiarEmpresa } = useSesion();
  const [empresas, setEmpresas] = useState<Empresa[] | null>(null);
  const [error, setError] = useState(false);
  const [cambiando, setCambiando] = useState<number | null>(null);

  const cargar = useCallback(async () => {
    try {
      setError(false);
      const respuesta = await get<{ items: Empresa[] }>("/api/v1/companies");
      setEmpresas(respuesta.items ?? []);
    } catch {
      setEmpresas(null);
      setError(true);
    }
  }, []);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const activa = contexto?.empresa.id ?? null;

  return (
    <section className="space-y-4">
      <header>
        <h1 className="text-2xl font-bold text-slate-900">Empresas</h1>
        <p className="text-sm text-slate-600">
          Las empresas a las que tienes acceso. Al cambiar, se actualiza toda la
          aplicación, incluido el ejercicio activo.
        </p>
      </header>

      {error && (
        <div role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          No se pudo cargar el listado de empresas.
          <button
            type="button"
            onClick={() => void cargar()}
            className="ml-3 rounded border border-red-300 px-2 py-0.5 text-xs hover:bg-red-100 focus-visible:outline-2 focus-visible:outline-red-700"
          >
            Reintentar
          </button>
        </div>
      )}

      {empresas === null && !error && (
        <p role="status" className="text-sm text-slate-500">
          Cargando empresas…
        </p>
      )}

      {empresas !== null && empresas.length === 0 && (
        <p className="text-sm text-slate-500">
          No tienes ninguna empresa asignada todavía.
        </p>
      )}

      {empresas !== null && empresas.length > 0 && (
        <ul className="divide-y divide-slate-100 overflow-hidden rounded-lg border border-slate-200 bg-white">
          {empresas.map((empresa) => {
            const esActiva = empresa.company_id === activa;
            return (
              <li key={empresa.company_id} className="flex items-center justify-between gap-4 p-4">
                <div className="min-w-0">
                  <p className="truncate font-medium text-slate-900">
                    {empresa.razon_social}
                    {esActiva && (
                      <span className="ml-2 rounded bg-emerald-100 px-1.5 py-0.5 text-xs text-emerald-800">
                        activa
                      </span>
                    )}
                  </p>
                  {empresa.nif && (
                    <p className="text-sm text-slate-500">{empresa.nif}</p>
                  )}
                </div>
                <button
                  type="button"
                  disabled={esActiva || cambiando !== null}
                  onClick={() => {
                    setCambiando(empresa.company_id);
                    void cambiarEmpresa(empresa.company_id).finally(() => setCambiando(null));
                  }}
                  className="shrink-0 rounded border border-slate-300 px-3 py-1 text-sm text-slate-700 hover:border-slate-500 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-slate-900"
                >
                  {esActiva ? "Actual" : "Cambiar a esta"}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
