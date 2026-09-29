"use client";

/**
 * MENU DE SESION (correcion provisional, 2026-09-29)
 *
 * La zona de contexto de arriba mostraba empresa, ejercicio y usuario, pero solo
 * la empresa y el ejercicio tenian desplegable (los dos selectores de la izquierda).
 * El usuario no tenia ninguna accion, y en particular **no habia forma de cerrar
 * sesion en ningun sitio de la aplicacion**. Este componente es ese sitio.
 *
 * Que hace, y por que esta duplicado en vez de ser el unico selector:
 *
 * - `CompanySwitcher` y `ExerciseSwitcher` siguen montados a la izquierda,
 *   porque son el camino rapido y porque llevan cosas que aqui no caben: el
 *   contador de asientos por ejercicio, el atajo al ejercicio anterior abierto y el
 *   motivo por el que un ejercicio cerrado no es seleccionable (SPEC-031
 *   FR-017/FR-031). Este menu no las quita ni las mueve.
 * - Aqui se reunen las tres acciones en un solo sitio, que es lo que se pedia.
 *   Delega la eleccion en `useSesion().cambiarEmpresa` / `cambiarEjercicio`, que es
 *   donde vive la logica (escribir el almacen **antes** de recargar). Lo unico que
 *   se reimplementa es pintar la lista, y para el estado del ejercicio se
 *   reutilizan `etiqueta` y `clase` de `ExerciseSwitcher`: que el color vaya
 *   acompanado de texto es FR-031, y dos copias de esa regla se separan.
 */

import { useEffect, useId, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { limpiarSesion } from "@/services/client";
import { setEjercicioActivo } from "./ejercicio";
import { useSesion } from "./SessionContext";
import { clase, etiqueta } from "./ExerciseSwitcher";
import type { EmpresaResumen } from "./CompanySwitcher";

export default function SessionMenu({ empresas }: { empresas: EmpresaResumen[] }) {
  const { contexto, cambiarEmpresa, cambiarEjercicio } = useSesion();
  const router = useRouter();
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

  /**
   * Cierre de sesion. El orden importa y no es cosmetico: `limpiarSesion()` borra
   * la empresa activa, y `setEjercicioActivo(null)` solo puede borrar la entrada si
   * todavia sabe cual es la empresa. Al reves, el ejercicio elegido se queda en
   * `localStorage` y el siguiente usuario de la misma maquina abre la aplicacion
   * en el ejercicio que eligio el anterior.
   */
  const salir = () => {
    setEjercicioActivo(null);
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
        className="flex items-center gap-2 rounded bg-slate-100 px-2 py-1 text-sm hover:bg-slate-200 focus-visible:outline-2 focus-visible:outline-slate-900"
      >
        <span className="max-w-[10rem] truncate">{usuario.nombre}</span>
        {usuario.rol && <span className="text-xs text-slate-500">{usuario.rol}</span>}
        <svg aria-hidden="true" viewBox="0 0 10 6" className="h-1.5 w-2.5 shrink-0 text-slate-400">
          <path d="M0 0h10L5 6z" fill="currentColor" />
        </svg>
      </button>

      {abierto && (
        <div
          id={panelId}
          role="menu"
          aria-label="Sesion"
          className="absolute right-0 z-40 mt-1 w-80 rounded border border-slate-200 bg-white p-2 shadow-lg"
        >
          <div className="border-b border-slate-100 px-2 pb-2">
            <p className="truncate text-sm font-semibold">{usuario.nombre}</p>
            <p className="truncate text-xs text-slate-500">{usuario.email}</p>
            {usuario.rol && <p className="text-xs text-slate-500">Rol: {usuario.rol}</p>}
          </div>

          <button
            type="button"
            role="menuitem"
            aria-expanded={seccion === "empresa"}
            onClick={() => setSeccion(seccion === "empresa" ? null : "empresa")}
            className="mt-1 flex w-full items-center justify-between rounded px-2 py-2 text-left text-sm hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-slate-900"
          >
            <span>Cambiar de empresa</span>
            <span className="text-xs text-slate-500">
              {unaEmpresa ? "sin otras empresas" : `${empresas.length} disponibles`}
            </span>
          </button>
          {seccion === "empresa" && (
            <ul role="menu" aria-label="Empresa activa" className="mb-1 ml-2 border-l border-slate-200 pl-2">
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
                      className="flex w-full items-baseline justify-between gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-slate-900"
                    >
                      <span className={activa ? "font-semibold" : ""}>{e.razon_social}</span>
                      {e.nif && <span className="shrink-0 text-xs text-slate-500">{e.nif}</span>}
                    </button>
                  </li>
                );
              })}
              {unaEmpresa && (
                <li className="px-2 py-1 text-xs text-slate-500">
                  Esta es la unica empresa a la que tienes acceso.
                </li>
              )}
            </ul>
          )}

          <button
            type="button"
            role="menuitem"
            aria-expanded={seccion === "ejercicio"}
            onClick={() => setSeccion(seccion === "ejercicio" ? null : "ejercicio")}
            className="flex w-full items-center justify-between rounded px-2 py-2 text-left text-sm hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-slate-900"
          >
            <span>Cambiar de ejercicio</span>
            <span className="text-xs text-slate-500">activo {contexto.ejercicio_activo.ejercicio}</span>
          </button>
          {seccion === "ejercicio" && (
            <ul role="menu" aria-label="Ejercicio activo" className="mb-1 ml-2 border-l border-slate-200 pl-2">
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
                        "flex w-full items-center justify-between gap-2 rounded px-2 py-1.5 text-left text-sm",
                        e.es_seleccionable
                          ? "hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-slate-900"
                          : "cursor-not-allowed opacity-60",
                      ].join(" ")}
                    >
                      <span className={clase(e)}>
                        {e.ejercicio}
                        {texto && <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs">{texto}</span>}
                      </span>
                      <span className="text-xs text-slate-500">{e.n_asientos}</span>
                    </button>
                  </li>
                );
              })}
              {ejercicios.length === 0 && (
                <li className="px-2 py-1 text-xs text-slate-500">La empresa no tiene ejercicios.</li>
              )}
            </ul>
          )}

          <div className="mt-1 border-t border-slate-100 pt-1">
            <button
              type="button"
              role="menuitem"
              onClick={salir}
              className="flex w-full items-center gap-2 rounded px-2 py-2 text-left text-sm text-red-700 hover:bg-red-50 focus-visible:outline-2 focus-visible:outline-red-700"
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
