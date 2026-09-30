"use client";

/**
 * LANDING DE TESORERÍA (SPEC-031, US5, T053)
 *
 * Antes esta página era un panel con cartera de efectos y últimos cobros por medio. Ya
 * no lo es, y el motivo es que **duplicaba** lo que hay en `/efectos` y
 * `/tesoreria/cobros`, que son destinos de esta misma superficie. Dos pantallas con la
 * misma información y dos listas de destinos que mantener es exactamente el problema que
 * la spec viene a resolver.
 *
 * Sus enlaces apuntaban además a `/tesoreria/efe`, una ruta que se retira en T057: el
 * flujo de efectivo pasa a `/tesoreria/flujos-efectivo` y esa entrada de aquí habría sido
 * un enlace a una pantalla que deja de existir.
 *
 * El resumen y la lista de destinos los monta `SurfacePanel` desde el layout raíz: el
 * panel deduce la superficie por la ruta, ve que `/tesoreria` es su landing y monta el
 * `ResumenSuperficie` de la tesorería. Por eso esta página no necesita saber nada de
 * resúmenes.
 */

export default function TesoreriaPage() {
  return (
    <section className="space-y-2">
      <h1 className="text-2xl font-bold text-white">Tesorería</h1>
      <p className="text-sm text-slate-400">
        Cobros y pagos, Efectos, anticipos, cesiones, conciliación, previsión de
        tesorería y flujo de efectivo del ejercicio activo.
      </p>
    </section>
  );
}
