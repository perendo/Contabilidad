/**
 * GUARD DE SESION (SPEC-031, research D2)
 *
 * POR QUE ESTO NO ES UN CONTROL DE SEGURIDAD
 *
 * El runtime Edge no puede leer `localStorage` ni verificar el JWT, asi que lo
 * unico que puede hacer es comprobar que existe la cookie y redirigir. Eso es una
 * redireccion OPTIMISTA: evita el fogonazo de una pantalla de negocio pintada sin
 * sesion, que es lo que pide FR-001, y nada mas.
 *
 * La frontera de seguridad real, antes y despues de esta feature, es el 401 del
 * backend. Un usuario sin cookie que se saltase esto (borrando la cookie) seguiria
 * sin poder leer ni escribir nada. Este fichero no relaja nada.
 *
 * El caso de cookie presente pero token caducado lo cubre `SessionGuard` en el
 * cliente, que ve el 401 y limpia la sesion. El token caduca a los 30 minutos, de
 * modo que ese caso es frecuente en uso diario.
 */

import { NextResponse, type NextRequest } from "next/server";

import { COOKIE_SESION } from "@/lib/constantes-sesion";

/** Rutas accesibles sin sesion. La de la propia pantalla de identificacion. */
const PUBLICAS = ["/login"];

/** Ficheros estaticos que no pasan por el guard. */
const EXCLUIDAS = [
  "/_next/static",
  "/_next/image",
  "/favicon.ico",
  "/api/sesion",
];

export function middleware(peticion: NextRequest): NextResponse {
  const ruta = peticion.nextUrl.pathname;

  if (EXCLUIDAS.some((prefijo) => ruta.startsWith(prefijo))) {
    return NextResponse.next();
  }
  if (PUBLICAS.includes(ruta)) {
    return NextResponse.next();
  }
  if (peticion.cookies.get(COOKIE_SESION)?.value) {
    return NextResponse.next();
  }

  // Se devuelve la ruta original para que la pantalla de identificacion pueda
  // devolver al usuario a donde queria ir.
  const destino = peticion.nextUrl.clone();
  destino.pathname = "/login";
  destino.search = "";
  destino.searchParams.set("next", ruta);
  return NextResponse.redirect(destino);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|api/sesion).*)"],
};
