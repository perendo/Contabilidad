/**
 * CONSTANTES DE SESION (SPEC-031)
 *
 * Modulo sin dependencias, compartido por `app/api/sesion/route.ts` (runtime
 * Node) y `middleware.ts` (runtime Edge).
 *
 * POR QUE NO SE IMPORTA DIRECTAMENTE DEL ROUTE HANDLER: el route handler corre en
 * Node y el middleware en Edge. Un import entre los dos mezcla runtimes en el
 * bundle de Edge. `tsc` no lo detecta; `next build` si, y el fallo aparece alli y
 * no aqui. La constante vive aqui y los dos la consumen.
 */

/** Cookie de sesion. Distinta de la clave de `localStorage` a proposito. */
export const COOKIE_SESION = "sesion_token";

/** El JWT caduca en 30 minutos (SPEC-003). La cookie dura mas a proposito. */
export const MAX_AGE_SESION_SEGUNDOS = 60 * 60 * 8;
