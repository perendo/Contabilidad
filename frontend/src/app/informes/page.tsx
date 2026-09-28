"use client";

/**
 * LANDING DE INFORMES (SPEC-031, US5, T049)
 *
 * La página deliberadamente no trae nada de contenido propio. El `SurfacePanel` del
 * layout raíz ya monta, en la landing de cada superficie:
 *
 * 1. los favoritos;
 * 2. el **resumen** del ejercicio activo, que viene de `GET /api/v1/resumenes/informes`;
 * 3. la lista de destinos de la superficie, ya filtrada por permisos.
 *
 * Añadir aquí una segunda fuente de datos produciría dos versiones de la misma pregunta
 * con dos criterios de aislamiento, y la mas fragil de mantener. La landing es el sitio donde se entra;
 * los datos los pone el panel.
 *
 * INFORMES: información de la superficie y acceso a su resumen.
 */

export default function InformesPage() {
  return (
    <section className="space-y-2">
      <h1 className="text-2xl font-bold text-slate-900">Informes</h1>
      <p className="text-sm text-slate-600">Estado de formulación de las cuentas anuales y el acceso a balance, PyG y demás informes.</p>
    </section>
  );
}
