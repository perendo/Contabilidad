"use client";

/**
 * AJUSTE DE INFORMACIÓN FISCAL (SII) (SPEC-031, US5, T071, FR-029)
 *
 * Vive como **sección** de la landing de Maestros y **no tiene ruta propia**, por dos
 * razones que el enunciado de T071 ya fija. La primera es de navegación: son tres campos
 * y un interruptor, y darle una entrada en el rail sería convertir un ajuste a la
 * categoría de un destino de trabajo. La segunda es de mantenimiento: una pantalla para
 * tres campos es una pantalla que hay que registrar, enlazar, filtrar por permisos y
 * documentar, para poco.
 *
 * Consume los endpoints que ya existen, de SPEC-012 y SPEC-029:
 *
 *   GET  /api/v1/sii/configuracion   (fiscal:ver)
 *   POST /api/v1/sii/configuracion   (fiscal:configurar)
 *
 * No se ha creado endpoint nuevo. El ajuste ya se podía configurar; lo que faltaba era
 * que se pudiera **encontrar**, y por eso esto es navegación y no API.
 *
 * El guardado es explícito y con botón, no automático al cambiar el interruptor. Es
 * deliberado: un ajuste fiscal que se guarda solo al mover un interruptor es un ajuste
 * que se cambia sin querer, y `fiscal:configurar` es un permiso de ADMIN.
 */

import { useCallback, useEffect, useState } from "react";

import { get, post } from "@/services/client";

interface ConfigSii {
  habilitado: boolean;
  obligatorio: boolean;
  identificador_emisor: string | null;
  periodicidad_303: string;
}

export default function AjusteSii() {
  const [config, setConfig] = useState<ConfigSii | null>(null);
  const [error, setError] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);
  // El permiso decide si se muestra el botón, no si se puede guardar. Ocultarlo del todo
  // haría que un ADMIN sin el permiso no entendiera por qué falta.
  const [puedeConfigurar, setPuedeConfigurar] = useState(false);

  const cargar = useCallback(async () => {
    try {
      setError(false);
      setConfig(await get<ConfigSii>("/api/v1/sii/configuracion"));
      const permisos = await get<{
        permisos?: { modulo: string; operacion: string }[];
      }>("/api/v1/permisos/mis-permisos");
      setPuedeConfigurar(
        (permisos.permisos ?? []).some(
          (p) => p.modulo === "fiscal" && p.operacion === "configurar",
        ),
      );
    } catch {
      setConfig(null);
      setError(true);
    }
  }, []);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const guardar = async () => {
    if (config === null) return;
    setGuardando(true);
    setAviso(null);
    try {
      await post("/api/v1/sii/configuracion", {
        habilitado: config.habilitado,
        identificador_emisor: config.identificador_emisor,
        obligatorio: config.obligatorio,
      });
      setAviso("Guardado.");
    } catch {
      setAviso("No se pudo guardar. Revisa que tengas permiso para configurarlo.");
    } finally {
      setGuardando(false);
    }
  };

  return (
    <section aria-labelledby="ajuste-sii" className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 id="ajuste-sii" className="text-sm font-semibold text-slate-900">
        Información fiscal electrónica (SII)
      </h2>

      {error && (
        <p role="alert" className="mt-2 text-sm text-amber-800">
          No se pudo leer la configuración fiscal.
          <button
            type="button"
            onClick={() => void cargar()}
            className="ml-2 rounded border border-amber-300 px-2 py-0.5 text-xs hover:bg-amber-50 focus-visible:outline-2 focus-visible:outline-amber-800"
          >
            Reintentar
          </button>
        </p>
      )}

      {config !== null && (
        <div className="mt-3 space-y-3">
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={config.habilitado}
              onChange={(e) => setConfig({ ...config, habilitado: e.target.checked })}
              className="h-4 w-4 rounded border-slate-300 focus-visible:outline-2 focus-visible:outline-slate-900"
            />
            Enviar las operaciones a la AEAT
          </label>

          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={config.obligatorio}
              onChange={(e) => setConfig({ ...config, obligatorio: e.target.checked })}
              className="h-4 w-4 rounded border-slate-300 focus-visible:outline-2 focus-visible:outline-slate-900"
            />
            Bloquear la facturación hasta enviar la operación
          </label>

          <label className="block text-sm text-slate-700">
            Identificador del emisor
            <input
              type="text"
              maxLength={20}
              value={config.identificador_emisor ?? ""}
              onChange={(e) =>
                setConfig({
                  ...config,
                  identificador_emisor: e.target.value === "" ? null : e.target.value,
                })
              }
              className="mt-1 block w-48 rounded border border-slate-300 px-2 py-1 text-sm focus-visible:outline-2 focus-visible:outline-slate-900"
            />
          </label>

          <p className="text-xs text-slate-500">
            Modelo 303 {config.periodicidad_303 === "MES" ? "mensual" : "trimestral"}.
          </p>

          {puedeConfigurar && (
            <button
              type="button"
              disabled={guardando}
              onClick={() => void guardar()}
              className="rounded bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-slate-900"
            >
              {guardando ? "Guardando…" : "Guardar"}
            </button>
          )}

          {!puedeConfigurar && (
            <p className="text-xs text-slate-500">
              Puedes ver el ajuste, pero no modificarlo: requiere el permiso de configurar.
            </p>
          )}

          {aviso && <p className="text-xs text-slate-600">{aviso}</p>}
        </div>
      )}
    </section>
  );
}
