"use client";

/**
 * MENU DE SESION (SPEC-031, US1, T085-T087)
 *
 * Alto contraste: botón de fondo blanco con texto negro, y menú desplegable con
 * fondo blanco, texto negro y opciones activas en azul con texto blanco.
 */

import { useEffect, useId, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { limpiarSesion } from "@/services/client";
import { setEjercicioActivo } from "./ejercicio";
import { useSesion } from "./SessionContext";
import { clase, etiqueta } from "./ExerciseSwitcher";
import type { EmpresaResumen } from "./CompanySwitcher";

export default function SessionMenu({ empresas }: { empresas: EmpresaResumen[] }) {
  const router = useRouter();
  const { contexto, cambiarEmpresa, cambiarEjercicio } = useSesion();
  const [abierto, setAbierto] = useState(false);
  const [seccion, setSeccion] = useState<"empresa" | "ejercicio" | null>(null);
  const contenedor = useRef<HTMLDivElement>(null);
  const boton = useRef<HTMLButtonElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!abierto) return;
    const fuera = (evento: MouseEvent) => {
      if (!contenedor.current?.contains(evento.target as Node)) setAbierto(false);
    };
    const alEsc = (evento: KeyboardEvent) => {
      if (evento.key !== "Escape") return;
      setAbierto(false);
      setSeccion(null);
      boton.current?.focus();
    };
    document.addEventListener("mousedown", fuera);
    document.addEventListener("keydown", alEsc);
    return () => {
      document.removeEventListener("mousedown", fuera);
      document.removeEventListener("keydown", alEsc);
    };
  }, [abierto]);

  const cerrar = () => {
    setAbierto(false);
    setSeccion(null);
    boton.current?.focus();
  };

  const salir = () => {
    try {
      setEjercicioActivo(null);
    } catch {
      // Ignorar si el storage no está disponible
    }
    limpiarSesion();
    setAbierto(false);
    router.push("/login");
  };

  const alTeclado = (evento: React.KeyboardEvent) => {
    if (evento.key === "ArrowDown" || evento.key === "Enter" || evento.key === " ") {
      if (!abierto) {
        evento.preventDefault();
        setAbierto(true);
        return;
      }
    }
    if (evento.key === "Escape") {
      setAbierto(false);
      setSeccion(null);
      boton.current?.focus();
    }
  };

  if (!contexto) return null;
  const { usuario } = contexto;
  const unaEmpresa = empresas.length <= 1;
  const ejercicios = contexto.ejercicios;

  return (
    <div ref={contenedor} className="relative">
      <button
        ref={boton}
        type="button"
        onClick={() => setAbierto((v) => !v)}
        onKeyDown={alTeclado}
        aria-haspopup="menu"
        aria-expanded={abierto}
        aria-controls={abierto ? panelId : undefined}
        title={`${usuario.email}${usuario.rol ? ` · ${usuario.rol}` : ""}`}
        className="flex items-center gap-2 bg-white border border-slate-300 px-3 py-1.5 rounded-lg text-xs font-semibold text-slate-900 shadow-sm hover:bg-slate-50 hover:border-slate-400 focus-visible:outline-2 focus-visible:outline-blue-600 transition-all"
      >
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="w-4 h-4 text-slate-700 shrink-0"
        >
          <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
          <circle cx="12" cy="7" r="4" />
        </svg>

        <span className="font-mono text-xs font-bold truncate max-w-[12rem] text-slate-900">
          {usuario.email || usuario.nombre}
        </span>

        {usuario.rol && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 font-mono font-bold border border-slate-300">
            {usuario.rol}
          </span>
        )}

        <svg aria-hidden="true" viewBox="0 0 10 6" className="h-1.5 w-2 shrink-0 text-slate-600 ml-1">
          <path d="M0 0h10L5 6z" fill="currentColor" />
        </svg>
      </button>

      {/* Desplegable con alto contraste: fondo blanco, texto negro, y selección azul con texto blanco */}
      {abierto && (
        <div
          id={panelId}
          role="menu"
          aria-label="Sesion"
          className="absolute right-0 top-full z-50 mt-1 w-80 rounded-xl border border-slate-300 bg-white p-2 shadow-2xl text-slate-900"
        >
          <div className="border-b border-slate-200 px-3 py-2">
            <p className="truncate text-xs font-bold text-black">{usuario.nombre}</p>
            <p className="truncate font-mono text-[11px] text-slate-600">{usuario.email}</p>
            {usuario.rol && <p className="text-[11px] text-slate-700 mt-0.5 font-semibold">Rol: {usuario.rol}</p>}
          </div>

          <button
            type="button"
            role="menuitem"
            aria-expanded={seccion === "empresa"}
            onClick={() => setSeccion(seccion === "empresa" ? null : "empresa")}
            className="mt-1 flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-xs font-semibold text-slate-900 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-blue-600"
          >
            <span>Cambiar de empresa</span>
            <span className="text-[11px] text-slate-500 font-normal">
              {unaEmpresa ? "sin otras empresas" : `${empresas.length} disponibles`}
            </span>
          </button>

          {seccion === "empresa" && (
            <ul role="menu" aria-label="Empresa activa" className="mb-1 ml-2 border-l-2 border-slate-300 pl-2 space-y-1">
              {empresas.map((e) => {
                const activa = e.company_id === contexto.empresa.id;
                return (
                  <li key={e.company_id} role="none">
                    <button
                      type="button"
                      role="menuitemradio"
                      aria-checked={activa}
                      onClick={async () => {
                        cerrar();
                        if (!activa) await cambiarEmpresa(e.company_id);
                      }}
                      className={[
                        "flex w-full items-baseline justify-between gap-2 rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors font-medium",
                        activa
                          ? "bg-blue-600 text-white font-bold shadow-sm"
                          : "text-slate-900 hover:bg-slate-100",
                      ].join(" ")}
                    >
                      <span>{e.razon_social}</span>
                      {e.nif && (
                        <span
                          className={[
                            "shrink-0 font-mono text-[10px]",
                            activa ? "text-blue-100 font-semibold" : "text-slate-500",
                          ].join(" ")}
                        >
                          {e.nif}
                        </span>
                      )}
                    </button>
                  </li>
                );
              })}
              {unaEmpresa && (
                <li className="px-2 py-1 text-[11px] text-slate-500">
                  Esta es la única empresa a la que tienes acceso.
                </li>
              )}
            </ul>
          )}

          <button
            type="button"
            role="menuitem"
            aria-expanded={seccion === "ejercicio"}
            onClick={() => setSeccion(seccion === "ejercicio" ? null : "ejercicio")}
            className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-xs font-semibold text-slate-900 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-blue-600"
          >
            <span>Cambiar de ejercicio</span>
            <span className="text-[11px] text-slate-500 font-normal">activo {contexto.ejercicio_activo.ejercicio}</span>
          </button>

          {seccion === "ejercicio" && (
            <ul role="menu" aria-label="Ejercicio activo" className="mb-1 ml-2 border-l-2 border-slate-300 pl-2 space-y-1">
              {ejercicios.map((e) => {
                const texto = etiqueta(e.estado, e.es_actual);
                const activo = e.ejercicio === contexto.ejercicio_activo.ejercicio;
                return (
                  <li key={e.ejercicio} role="none">
                    <button
                      type="button"
                      role="menuitemradio"
                      aria-checked={activo}
                      aria-disabled={!e.es_seleccionable}
                      title={!e.es_seleccionable ? "No admite asientos" : undefined}
                      disabled={!e.es_seleccionable}
                      onClick={async () => {
                        cerrar();
                        if (!activo) await cambiarEjercicio(e.ejercicio);
                      }}
                      className={[
                        "flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors font-medium",
                        !e.es_seleccionable
                          ? "cursor-not-allowed opacity-50 text-slate-400"
                          : activo
                          ? "bg-blue-600 text-white font-bold shadow-sm"
                          : "text-slate-900 hover:bg-slate-100",
                      ].join(" ")}
                    >
                      <span className={activo ? "text-white font-bold" : clase(e)}>
                        {e.ejercicio}
                        {texto && (
                          <span
                            className={[
                              "ml-2 rounded px-1.5 py-0.5 text-[10px] font-semibold",
                              activo
                                ? "bg-blue-800 text-white border border-blue-400"
                                : "bg-amber-100 text-amber-900 border border-amber-300",
                            ].join(" ")}
                          >
                            {texto}
                          </span>
                        )}
                      </span>
                      <span
                        className={[
                          "font-mono text-[11px]",
                          activo ? "text-blue-100 font-semibold" : "text-slate-500",
                        ].join(" ")}
                      >
                        {e.n_asientos}
                      </span>
                    </button>
                  </li>
                );
              })}
              {ejercicios.length === 0 && (
                <li className="px-2 py-1 text-[11px] text-slate-500">La empresa no tiene ejercicios.</li>
              )}
            </ul>
          )}

          <div className="mt-2 border-t border-slate-200 pt-2">
            <button
              type="button"
              role="menuitem"
              onClick={salir}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs font-semibold text-rose-700 hover:bg-rose-50 focus-visible:outline-2 focus-visible:outline-rose-500 transition-colors"
            >
              <svg aria-hidden="true" viewBox="0 0 16 16" className="h-4 w-4 fill-current">
                <path d="M6 1H3a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h3v-1.5H3.5V2.5H6V1Zm7.3 4.3-1.1-1.1L10.4 6H7v4h3.4l-1.8 1.8 1.1 1.1L14 9l-3.7-3.7Z" />
              </svg>
              Cerrar sesión
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
