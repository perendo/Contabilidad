"use client";

/**
 * LANDING DE MAESTROS (SPEC-031, US5, T051 y T071)
 *
 * La página deliberadamente no trae nada de contenido propio. El `SurfacePanel` del
 * layout raíz ya monta, en la landing de cada superficie:
 *
 * 1. los favoritos;
 * 2. el **resumen** del ejercicio activo, que viene de `GET /api/v1/resumenes/{CLAVE}`;
 * 3. la lista de destinos de la superficie, ya filtrada por permisos.
 *
 * Añadir aquí una segunda fuente de datos produciría dos versiones de la misma pregunta
 * con dos criterios de aislamiento, y la que más frágil de mantener. La landing es el
 * sitio donde se entra; los datos los pone el panel.
 *
 * MAESTROS: información de la superficie y acceso a su resumen.
 *
 * El ajuste de SII (T071, FR-029) es la **única** excepción: vive aquí como sección y
 * no tiene ruta propia, porque son tres campos y no un destino de trabajo. Ver
 * `AjusteSii` para por qué no es un destino más.
 *
 * El `id` lo declara el mapa de superficies (`Destino.ancla`), no esta página, y por
 * eso se pasa en vez de estar escrito aquí: el enlace del panel se compone como
 * `/maestros#ajustes-sii`, y si el ancla viviera solo en un lado, cambiarla en el otro
 * dejaría un enlace que no lleva a ninguna parte sin que nada fallara.
 */

import AjusteSii from "@/components/navigation/AjusteSii";

export default function MaestrosPage() {
  return (
    <div className="space-y-6">
      <section className="space-y-2">
        <h1 className="text-2xl font-bold text-slate-900">Maestros</h1>
        <p className="text-sm text-slate-600">
          Empresas, terceros, plan de cuentas y catálogos que alimentan el resto de la
          aplicación.
        </p>
      </section>
      <AjusteSii id="ajustes-sii" />
    </div>
  );
}
