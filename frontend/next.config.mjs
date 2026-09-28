/** @type {import('next').NextConfig} */
const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

/**
 * REDIRECTS PERMANENTES (SPEC-031, US6, T055)
 *
 * Se declaran aquí y no como páginas que redirijan con JavaScript, por una razón que no
 * es estética: `next.config.mjs` se resuelve ANTES del enrutado y del middleware, así
 * que una dirección antigua contesta 308 sin montar React, sin pedir la sesión y sin
 * ejecutar una línea del shell. Una página que hiciese lo mismo dejaría al usuario ver
 * un instante la pantalla anterior, o un blanco mientras carga.
 *
 * `permanent: true` produce 308 y no 301. La diferencia importa aunque aquí ambas valdrían
 * (todas son rutas de lectura): el 308 conserva método y cuerpo, y el 301 obliga al
 * cliente a convertir a GET. Un cambio de ubicación permanente es 308.
 *
 * POR QUÉ HAY UN SOLO REDIRECT Y NO CINCO
 * ---------------------------------------
 *
 * T055 pedía cinco y T057 borrar cinco pantallas. Al mirar el contenido de cada una
 * resultó que **cuatro no eran duplicados**: tenían una función que su destino canónico
 * no tiene.
 *
 *   - `/cierre` tiene el botón "Cerrar" sobre `fiscal-years/{year}/close` (SPEC-004). La
 *     landing `/cierres` es un índice con tres tarjetas, sin ninguna acción.
 *   - `/cobros` lista los cobros registrados contra un vencimiento. `/vencimientos` lista
 *     vencimientos y permite cobrar, pero no enseña ese detalle.
 *   - `/tesoreria/efe` tiene el botón "Formular" del informe de flujos de efectivo
 *     (SPEC-027). `/efe` es otra pantalla distinta: el *estado* de flujos de efectivo
 *     provisional y oficial (SPEC-010), sin ninguna acción.
 *
 * Borrarlas habría destruido tres funciones en producción, y en el caso de
 * `/tesoreria/efe` además una página que **no estaba en el mapa**: era inalcanzable desde
 * la navegación, que es un defecto distinto y peor que tener dos rutas parecidas. Las
 * tres se han añadido al mapa y se conservan. Ver el "Estado real" de `tasks.md`.
 *
 * El único movimiento real de ruta es el de import y export, que sí era el mismo código
 * en dos sitios, y se resolvió moviendo el fichero a la ruta canónica que fija
 * `surfaces.ts`.
 */
const REDIRECTS = [
  {
    source: "/contabilidad/import-export",
    destination: "/asientos/import-export",
  },
];

const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${backendUrl}/api/v1/:path*`,
      },
    ];
  },

  async redirects() {
    return REDIRECTS.map((r) => ({ ...r, permanent: true }));
  },
};

export default nextConfig;
