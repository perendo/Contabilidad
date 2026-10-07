"use client";

/**
 * MENU DE SESION Y CONTEXTO
 *
 * Muestra el usuario autenticado, su rol y las opciones de cambio de contexto
 * (empresa y ejercicio) y cierre de sesion.
 */

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSesion } from "./SessionContext";
import { setEjercicioActivo } from "./ejercicio";

export default function SessionMenu() {
  const router = useRouter();
  const { contexto, recargar } = useSesion();
  const [abierto, setAbierto] = useState(false);
  const [seccion, setSeccion] = useState<"empresa" | "ejercicio" | null>(null);
  const contenedor = useRef<HTMLDivElement>(null);

  // Cierre al pulsar fuera y con Escape
  useEffect(() => {
    function manejarClickFuera(e: MouseEvent) {
      if (contenedor.current && !contenedor.current.contains(e.target as Node)) {
        setAbierto(false);
        setSeccion(null);
      }
    }
    function manejarTecla(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setAbierto(false);
        setSeccion(null);
      }
    }
    document.addEventListener("mousedown", manejarClickFuera);
    document.addEventListener("keydown", manejarTecla);
    return () => {
      document.removeEventListener("mousedown", manejarClickFuera);
      document.removeEventListener("keydown", manejarTecla);
    };
  }, []);

  const empresas = contexto?.empresas || [];
  const empresaActiva = contexto?.empresa_activa;
  const ejercicioActivo = contexto?.ejercicio_activo;

  const cambiarEmpresa = async (id: number) => {
    try {
      localStorage.setItem("empresa_activa_id", String(id));
      await recargar();
      setAbierto(false);
      setSeccion(null);
      router.refresh();
    } catch (e) {
      console.error("Error al cambiar empresa", e);
    }
  };

  const cambiarEjercicio = async (anio: number) => {
    try {
      setEjercicioActivo(anio);
      await recargar();
      setAbierto(false);
      setSeccion(null);
      router.refresh();
    } catch (e) {
      console.error("Error al cambiar ejercicio", e);
    }
  };

  const cerrarSesion = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("empresa_activa_id");
    localStorage.removeItem("ejercicio_activo");
    router.push("/login");
  };

  if (!contexto) return null;
  const { usuario } = contexto;
  const unaEmpresa = empresas.length <= 1;
  const ejercicios = contexto.ejercicios;

  return (
    <div ref={contenedor} className="relative">
      <button
        onClick={() => setAbierto(!abierto)}
        aria-haspopup="true"
        aria-expanded={abierto}
        className="flex items-center gap-2 rounded-xl bg-white px-3 py-1.5 text-xs text-slate-900 shadow-sm border border-slate-300 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-blue-600 transition-colors font-medium"
      >
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-100 text-[10px] font-bold text-blue-800">
          {usuario?.email?.slice(0, 2).toUpperCase() || "US"}
        </span>
        <span className="font-semibold text-slate-900 max-w-[120px] truncate">{usuario?.email || "Usuario"}</span>
        <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4 text-slate-700">
          <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd" />
        </svg>
      </button>

      {abierto && (
        <div className="absolute right-0 mt-2 w-72 rounded-2xl bg-white p-2 shadow-2xl border border-slate-300 text-xs text-slate-900 z-50">
          <div className="px-3 py-2.5 border-b border-slate-200">
            <div className="font-bold text-slate-900 truncate">{usuario?.nombre || usuario?.email}</div>
            <div className="text-[11px] text-slate-600 font-mono flex items-center justify-between mt-0.5">
              <span>{usuario?.email}</span>
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-bold text-blue-700 border border-slate-200 uppercase">
                {usuario?.rol || "USUARIO"}
              </span>
            </div>
          </div>

          <button
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
                const activa = e.id === empresaActiva?.id;
                return (
                  <li key={e.id} role="none">
                    <button
                      role="menuitem"
                      onClick={() => cambiarEmpresa(e.id)}
                      className={[
                        "flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-xs text-left transition-colors font-medium",
                        activa
                          ? "bg-blue-600 text-white font-bold shadow-sm"
                          : "text-slate-800 hover:bg-slate-100",
                      ].join(" ")}
                    >
                      <span className="truncate">{e.razon_social || e.nombre}</span>
                      {activa && (
                        <span className="text-[10px] ml-1.5 font-bold text-white shrink-0">
                          ✓ Activa
                        </span>
                      )}
                    </button>
                  </li>
                );
              })}
              {unaEmpresa && (
                <li className="px-2 py-1 text-[11px] text-slate-500">
                  Esta es la única empresa a la que tienes acceso (unica empresa a la que tienes acceso).
                </li>
              )}
            </ul>
          )}

          <button
            onClick={() => setSeccion(seccion === "ejercicio" ? null : "ejercicio")}
            className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-xs font-semibold text-slate-900 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-blue-600"
          >
            <span>Cambiar de ejercicio</span>
            <span className="text-[11px] text-slate-500 font-mono font-normal">
              {ejercicioActivo ? `${ejercicioActivo.anio}` : "Sin seleccionar"}
            </span>
          </button>

          {seccion === "ejercicio" && (
            <ul role="menu" aria-label="Ejercicio activo" className="mb-1 ml-2 border-l-2 border-slate-300 pl-2 space-y-1">
              {ejercicios?.map((ej) => {
                const activo = ej.anio === ejercicioActivo?.anio;
                return (
                  <li key={ej.anio} role="none">
                    <button
                      role="menuitem"
                      onClick={() => cambiarEjercicio(ej.anio)}
                      className={[
                        "flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-xs text-left transition-colors font-medium",
                        activo
                          ? "bg-blue-600 text-white font-bold shadow-sm"
                          : "text-slate-800 hover:bg-slate-100",
                      ].join(" ")}
                    >
                      <span className="font-mono font-bold">{ej.anio}</span>
                      <span className={[
                        "text-[10px] font-mono",
                        activo ? "text-blue-100" : "text-slate-500",
                      ].join(" ")}>
                        {ej.estado} {activo && "✓"}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}

          <div className="mt-1 border-t border-slate-200 pt-1">
            <button
              onClick={cerrarSesion}
              className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-xs font-semibold text-rose-600 hover:bg-rose-50 transition-colors"
            >
              <span>Cerrar sesión</span>
              <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
                <path fillRule="evenodd" d="M3 4.25A2.25 2.25 0 015.25 2h5.5A2.25 2.25 0 0113 4.25v2a.75.75 0 01-1.5 0v-2a.75.75 0 00-.75-.75h-5.5a.75.75 0 00-.75.75v11.5c0 .414.336.75.75.75h5.5a.75.75 0 00.75-.75v-2a.75.75 0 011.5 0v2A2.25 2.25 0 0110.75 18h-5.5A2.25 2.25 0 013 15.75V4.25z" clipRule="evenodd" />
                <path fillRule="evenodd" d="M19 10a.75.75 0 00-.75-.75H8.704l2.473-2.47a.75.75 0 10-1.06-1.064l-3.75 3.75a.75.75 0 000 1.064l3.75 3.75a.75.75 0 101.06-1.064L8.704 10.75h9.546A.75.75 0 0019 10z" clipRule="evenodd" />
              </svg>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
