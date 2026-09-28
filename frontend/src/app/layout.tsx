import type { Metadata } from "next";

import AppShell from "../components/navigation/AppShell";
import ContextZone from "../components/navigation/ContextZone";
import { SessionProvider } from "../components/navigation/SessionContext";
import "./globals.css";

export const metadata: Metadata = {
  title: "Contabilidad",
  description: "Sistema de contabilidad multiempresa",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <body>
        {/* SPEC-031: el proveedor envuelve la zona de contexto y la pagina. El
            guard de sesion de baja capa es `src/middleware.ts`, que redirige antes
            de montar nada; este proveedor es quien sabe que empresa y que ejercicio
            estan activos y quien recalcula el contexto al cambiarlos.

            El `AppShell` va en el layout RAIZ a proposito: es lo que hace que las
            103 pantallas tengan navegacion sin que cada una la monte. Es un
            componente de cliente, y eso es correcto: el layout es de servidor y lo
            monta, pero el shell lee la sesion y el ancho de ventana, que solo
            existen en el cliente. */}
        <SessionProvider>
          <ContextZone />
          <AppShell>{children}</AppShell>
        </SessionProvider>
      </body>
    </html>
  );
}
