"use client";

/**
 * SHELL DE LA APLICACION (SPEC-031, T026)
 *
 * Compone la estructura de navegacion completa:
 *
 *     ┌──────────────────────────────────────────────┐
 *     │  ContextZone  (ya montada en layout.tsx)     │  zona de contexto
 *     ├────┬─────────────────────────────────────────┤
 *     │Rail│  SurfacePanel                           │  contenido
 *     │    │                                         │
 *     ├────┴─────────────────────────────────────────┤
 *     │  MobileNav (solo en compacto)               │  barra inferior
 *     └──────────────────────────────────────────────┘
 *
 * Los puntos de ruptura son los de M3 (research D1): en compacto hay barra inferior
 * y NO hay rail, porque M3 desaconseja el rail estandar en pantallas estrechas. A
 * partir de 640px aparece el rail y desaparece la barra.
 *
 * NOTA SOBRE EL 640px: M3 situa el corte compacto en 600dp. Aqui se usa 640 porque
 * es lo que usa Tailwind en su escala (`md`), y tener dos numeros distintos para lo
 * mismo invita a que se desincronicen. La diferencia de 40px no afecta a la decision
 * de componente.
 *
 * ACCESIBILIDAD: el rail y la barra inferior son dos `nav` con etiqueta distinta, para
 * que un lector de pantalla no anuncie los mismos destinos dos veces como si fueran
 * dos navegaciones diferentes. En compacto solo existe la barra, asi que solo se
 * anuncia una.
 *
 * LOS PERMISOS SE LEEN DE LA SESION, NO SE PASAN COMO PROPS: el shell se monta en el
 * layout raiz, que es un componente de servidor y no puede leer un hook de cliente.
 * Pedirle que bajara los permisos obligaria a que las 103 pantallas los recibieran
 * como prop y los repasaran, que es exactamente el prop drilling que se quiere
 * evitar.
 */

import type { ReactNode } from "react";

import DestinationRail from "./DestinationRail";
import MobileNav from "./MobileNav";
import SurfacePanel from "./SurfacePanel";
import { useSesion } from "./SessionContext";
import { usePathname } from "next/navigation";

export default function AppShell({
  children,
  acciones,
}: {
  children: ReactNode;
  /**
   * Ya NO lleva `resumen`. El resumen de cada superficie lo monta `SurfacePanel` a
   * partir de la ruta, porque el shell está en el layout raíz y no sabe qué superficie
   * está activa. Dejar la prop aquí habría creado dos maneras de hacer lo mismo, y la
   * que nadie usa.
   */
  acciones?: ReactNode;
}) {
  const { permisos } = useSesion();
  const pathname = usePathname();

  if (pathname === "/login") {
    return <main className="min-h-screen w-full">{children}</main>;
  }
  return (
    <div className="flex min-h-screen flex-col">
      <div className="flex flex-1">
        <DestinationRail permisos={permisos} />
        <SurfacePanel permisos={permisos} acciones={acciones}>
          {children}
        </SurfacePanel>
      </div>
      <MobileNav permisos={permisos} />
    </div>
  );
}
