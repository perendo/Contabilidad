/**
 * RUTA DE SESION (SPEC-031, research D2)
 *
 * POR QUE EXISTE ESTE FICHERO Y NO UN `document.cookie` DESDE EL NAVEGADOR:
 * JavaScript no puede crear una cookie `httpOnly`. Solo una respuesta del servidor
 * puede marcarla asi. Ponerla desde el cliente daria una cookie con el mismo
 * nombre pero sin esa proteccion, y el comentario prometeria algo que no seria
 * cierto. Un Route Handler de Next si es codigo de servidor.
 *
 * QUE HACE Y QUE NO HACE:
 *   - Al iniciar sesion, guarda el token en cookie `httpOnly` para que el
 *     `middleware.ts` pueda hacer su redireccion optimista.
 *   - NO es un control de seguridad. El middleware comprueba que la cookie
 *     existe; la verificacion real es el 401 del backend, que ya funciona. El
 *     token sigue en `localStorage` para el encabezado `Authorization`, porque el
 *     fetch del cliente necesita leerlo.
 */

import { NextResponse } from "next/server";

import {
  COOKIE_SESION,
  MAX_AGE_SESION_SEGUNDOS,
} from "@/lib/constantes-sesion";

// Un route handler de Next 15 solo puede exportar los metodos HTTP y unos pocos
// campos de configuracion. Reexportar una constante rompe el type check del build
// (`checkFields<{ [x: string]: never }>`), aunque `tsc --noEmit` pase. Por eso
// `COOKIE_SESION` vive en `lib/constantes-sesion.ts` y no se reexporta aqui.

export async function POST(peticion: Request): Promise<NextResponse> {
  let token = "";
  try {
    const cuerpo = (await peticion.json()) as { token?: unknown };
    if (typeof cuerpo.token === "string") token = cuerpo.token;
  } catch {
    token = "";
  }
  if (!token) {
    return NextResponse.json(
      { code: "token_ausente", detail: "No se ha recibido el token." },
      { status: 400 },
    );
  }
  const respuesta = NextResponse.json({ ok: true });
  respuesta.cookies.set({
    name: COOKIE_SESION,
    value: token,
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: MAX_AGE_SESION_SEGUNDOS,
  });
  return respuesta;
}

export async function DELETE(): Promise<NextResponse> {
  const respuesta = NextResponse.json({ ok: true });
  respuesta.cookies.set({
    name: COOKIE_SESION,
    value: "",
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 0,
  });
  return respuesta;
}
