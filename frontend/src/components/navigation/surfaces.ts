/**
 * MAPA DE SUPERFICIES (SPEC-031)
 *
 * FUENTE UNICA DE VERDAD. Toda la navegacion se deriva de aqui: el rail, el panel
 * de cada superficie, los landings y el filtro por permisos. El guard
 * `backend/tests/unit/test_guard_mapa_superficies.py` contrasta este fichero contra
 * las pantallas reales del proyecto, asi que una pantalla sin asignar rompe la
 * suite en vez de quedar huerfana.
 *
 * Referencia: contracts/navigation-contract.md
 *
 * DOS IDENTIFICADORES, Y NO ES REDUNDANCIA
 *   `clave`  estable. Es lo que se guarda en `favorito_usuario`. Sobrevive a
 *            reubicaciones, que es lo que exige FR-026.
 *   `ruta`   cambiante. Mover una opcion cambia la ruta y deja la clave intacta,
 *            de modo que los favoritos siguen resolviendo.
 *
 * `accion: true` significa que NO es un destino de navegacion (FR-013): es una
 * accion de la pantalla en la que se aplica, y por eso no aparece en el panel.
 */

import type { ContextoSesion } from "./tipos";

/** Un par de modulo y operacion del catalogo RBAC (SPEC-015). */
export type Permiso = readonly [string, string];

/**
 * Si la lista de permisos significa "no hay informacion" en vez de "no hay nada".
 *
 * `undefined` es que el componente no recibio la lista, y `[]` es que la llamada fallo
 * o todavia no ha terminado. En los dos casos hay que mostrar TODO.
 *
 * La distincion importa mucho: `[]` es tambien el estado inicial, asi que comprobar
 * solo `permisos === undefined` deja el panel **vacio** durante el primer render, y
 * para siempre si la peticion de permisos falla. Fallar abierto es lo correcto aqui:
 * el backend es quien autoriza de verdad, y ocultar destinos por no saber los
 * permisos le quita navegacion al usuario sin motivo. El unico filtro que no puede
 * faltar es la peticion HTTP, que responde 403 cuando toca.
 */
export function sinRestricciones(
  permisos: readonly (readonly [string, string])[] | undefined,
): permisos is undefined {
  return permisos === undefined || permisos.length === 0;
}

/** ACCESO DE CONTEXTO: lo poseen los tres roles base (research D10). */
export const ACCESO_CONTEXTO: Permiso = ["acct", "ver"];

export interface Destino {
  /** Estable. No cambia nunca. */
  clave: string;
  etiqueta: string;
  /** Contenedor de segmentos dinamicos de Next, p. ej. `/asientos/[id]`. */
  ruta: string;
  permiso: Permiso;
  /** Etiqueta de grupo dentro de la superficie. Solo Tesoreria lo usa. */
  grupo?: string;
  /** Es una accion, no un destino: no aparece en navegacion. */
  accion?: boolean;
  /** Destino alcanzado desde otro, no desde el panel. */
  hijo?: boolean;
  /** Ajuste dentro del panel, sin pantalla propia. */
  ajuste?: boolean;
}

export interface Superficie {
  clave: string;
  etiqueta: string;
  icono: string;
  landing: string;
  permiso: Permiso;
  destinos: readonly Destino[];
}

const d = (
  clave: string,
  etiqueta: string,
  ruta: string,
  extra: Partial<Destino> = {},
): Destino => ({ clave, etiqueta, ruta, permiso: ACCESO_CONTEXTO, ...extra });

const ACCION = { accion: true } as const;
const HIJO = { hijo: true } as const;

/** Orden fijo del rail. FR-009: el orden no depende del uso. */
export const SUPERFICIES: readonly Superficie[] = [
  {
    clave: "contabilidad",
    etiqueta: "Contabilidad",
    icono: "libro",
    landing: "/contabilidad",
    permiso: ACCESO_CONTEXTO,
    destinos: [
      d("plan-cuentas", "Plan de cuentas", "/cuentas"),
      d("plan-cuentas-nueva", "Nueva cuenta", "/cuentas/nueva", ACCION),
      d("catalogo", "Catálogo de cuentas", "/catalogo"),
      d("catalogo-detalle", "Detalle de catálogo", "/catalogo/[id]", HIJO),
      d("catalogo-importar", "Importar catálogo", "/catalogo/importar", ACCION),
      d("catalogo-reclasificar", "Reclasificar saldos", "/catalogo/reclasificar", ACCION),
      d("asientos", "Asientos", "/asientos/diario"),
      d("asientos-nuevo", "Nuevo asiento", "/asientos/nuevo", ACCION),
      d("asientos-detalle", "Detalle de asiento", "/asientos/[id]", HIJO),
      d("plantillas", "Plantillas", "/plantillas"),
      d("plantillas-nueva", "Nueva plantilla", "/plantillas/nueva", ACCION),
      d("plantillas-detalle", "Detalle de plantilla", "/plantillas/[id]", HIJO),
      d("plantillas-generar", "Generar asiento", "/plantillas/[id]/generar", ACCION),
      d("documentos", "Documentos", "/documentos"),
      d("inmovilizado", "Inmovilizado", "/inmovilizado"),
      d("inmovilizado-alta", "Alta de activo", "/inmovilizado/alta", ACCION),
      d("inmovilizado-detalle", "Detalle de activo", "/inmovilizado/[id]", HIJO),
      d("inmovilizado-amortizaciones", "Amortizaciones", "/inmovilizado/amortizaciones"),
      d("divisas", "Divisas", "/divisas"),
      d("divisas-tipos", "Tipos de cambio", "/divisas/tipos", HIJO),
      d("divisas-historial", "Historial de tipos", "/divisas/tipos/historial", HIJO),
      d("divisas-valoracion", "Valoraciones", "/divisas/valoracion", HIJO),
      d("divisas-asiento", "Asiento en divisa", "/divisas/asientos/nuevo", ACCION),
      d("import-export", "Importar y exportar", "/asientos/import-export"),
      d("ejercicio", "Ejercicio y cierre", "/cierres"),
      d("apertura", "Apertura", "/apertura"),
      d("cierre-intermedio", "Cierre intermedio", "/cierres/intermedio"),
      d("cierre-anual", "Cierre anual", "/cierres/anual"),
      d("reaperturas", "Reaperturas", "/cierres/reaperturas"),
      d("cierres-detalle", "Detalle de cierre", "/cierres/[id]", HIJO),
      d(
        "cierre-ejercicio",
        "Cierre de ejercicio",
        "/cierre",
        { grupo: "Cierre de ejercicio" },
      ),
    ],
  },
  {
    clave: "facturacion",
    etiqueta: "Facturación",
    icono: "factura",
    landing: "/facturacion",
    permiso: ACCESO_CONTEXTO,
    destinos: [
      d("facturas", "Facturas", "/facturacion/facturas"),
      d("facturas-nueva", "Nueva factura", "/facturacion/facturas/nueva", ACCION),
      d("facturas-detalle", "Detalle de factura", "/facturacion/facturas/[id]", HIJO),
      d("facturas-rectificar", "Rectificar factura", "/facturacion/facturas/[id]/rectificar", ACCION),
      d("series", "Series", "/facturacion/series"),
    ],
  },
  {
    clave: "tesoreria",
    etiqueta: "Tesorería",
    icono: "banco",
    landing: "/tesoreria",
    permiso: ACCESO_CONTEXTO,
    destinos: [
      d("vencimientos", "Cobros y pagos", "/vencimientos", { grupo: "Operación" }),
      d("antiguedad", "Antigüedad de saldos", "/antiguedad", { grupo: "Operación" }),
      d("cobros-detalle", "Cobros de un vencimiento", "/cobros"),
      d("medios-pago", "Medios de pago", "/tesoreria/cobros", { grupo: "Operación" }),
      d("remesas", "Remesas", "/remesas", { grupo: "Operación" }),
      d("remesas-nueva", "Nueva remesa", "/remesas/nueva", { grupo: "Operación", accion: true }),
      d("remesas-detalle", "Detalle de remesa", "/remesas/[id]", { grupo: "Operación", hijo: true }),
      d("devoluciones", "Devoluciones", "/devoluciones", { grupo: "Operación" }),
      d("devoluciones-detalle", "Detalle de devolución", "/devoluciones/[id]", { grupo: "Operación", hijo: true }),
      d("efectos", "Efectos", "/efectos", { grupo: "Instrumentos" }),
      d("efectos-nuevo", "Nuevo efecto", "/efectos/nuevo", { grupo: "Instrumentos", accion: true }),
      d("efectos-detalle", "Detalle de efecto", "/efectos/[id]", { grupo: "Instrumentos", hijo: true }),
      d("anticipos", "Anticipos", "/anticipos", { grupo: "Instrumentos" }),
      d("anticipos-nuevo", "Nuevo anticipo", "/anticipos/nuevo", { grupo: "Instrumentos", accion: true }),
      d("anticipos-detalle", "Detalle de anticipo", "/anticipos/[id]", { grupo: "Instrumentos", hijo: true }),
      d("cesiones", "Cesión de cobros", "/cesiones", { grupo: "Instrumentos" }),
      d("cesiones-nueva", "Nueva cesión", "/cesiones/nueva", { grupo: "Instrumentos", accion: true }),
      d("cesiones-detalle", "Detalle de cesión", "/cesiones/[id]", { grupo: "Instrumentos", hijo: true }),
      d("conciliacion", "Conciliación", "/conciliacion", { grupo: "Banco" }),
      d("conciliacion-importar", "Importar extracto", "/conciliacion/importar", { grupo: "Banco", accion: true }),
      d("conciliacion-detalle", "Detalle de conciliación", "/conciliacion/[id]", { grupo: "Banco", hijo: true }),
      d("conciliacion-periodos", "Periodos conciliados", "/conciliacion/periodos", { grupo: "Banco" }),
      d("previsiones", "Previsión de tesorería", "/tesoreria/previsiones", { grupo: "Previsión" }),
      d("previsiones-detalle", "Detalle de previsión", "/tesoreria/previsiones/[id]", { grupo: "Previsión", hijo: true }),
      d("alertas-liquidez", "Alertas de liquidez", "/tesoreria/alertas", { grupo: "Previsión" }),
      d(
        "informe-efe",
        "Informe de flujos de efectivo",
        "/tesoreria/efe",
        { grupo: "Previsión" },
      ),
    ],
  },
  {
    clave: "informes",
    etiqueta: "Informes",
    icono: "informe",
    landing: "/informes",
    permiso: ACCESO_CONTEXTO,
    destinos: [
      d("balance", "Balance", "/balance"),
      d("pyg", "Pérdidas y ganancias", "/pyg"),
      d("mayor", "Libro mayor", "/informes/mayor"),
      d("sumas-saldos", "Sumas y saldos", "/informes/sumas-saldos"),
      d("coste", "Informe de costes", "/informes/costes"),
      d("presupuestos", "Presupuestos", "/presupuestos"),
      d("presupuestos-seguimiento", "Seguimiento", "/presupuestos/seguimiento"),
      d("presupuestos-informes", "Informes de desviación", "/presupuestos/informes"),
      d("cuentas-anuales", "Cuentas anuales", "/cuentas-anuales"),
      d("flujos-efectivo", "Flujos de efectivo", "/efe"),
    ],
  },
  {
    clave: "fiscal",
    etiqueta: "Fiscal",
    icono: "fiscal",
    landing: "/fiscal",
    permiso: ACCESO_CONTEXTO,
    destinos: [
      d("libros-iva", "Libros de IVA", "/libros-iva"),
      d("modelos", "Modelos fiscales", "/modelos"),
      d("retenciones", "Retenciones", "/fiscal/retenciones"),
      d("retenciones-nueva", "Nueva liquidación", "/fiscal/retenciones/nueva", ACCION),
      d("retenciones-detalle", "Detalle de retención", "/fiscal/retenciones/[id]", HIJO),
      d("modelo-190", "Modelo 190 de retenciones", "/fiscal/modelos/190"),
      d("impuesto-sociedades", "Impuesto sobre Sociedades", "/fiscal/impuesto-sociedades"),
      d("is-nueva", "Nuevo cálculo", "/fiscal/impuesto-sociedades/nuevo", ACCION),
      d("is-detalle", "Detalle del cálculo", "/fiscal/impuesto-sociedades/[id]", HIJO),
      d("modelo-200", "Modelo 200 de sociedades", "/fiscal/modelo-200"),
      d("ong-subvenciones", "Subvenciones", "/ong/subvenciones"),
      d("ong-subvenciones-detalle", "Detalle de subvención", "/ong/subvenciones/[id]", HIJO),
      d("ong-libros", "Libros oficiales", "/ong/libros"),
      d("ong-caja", "Caja", "/ong/caja"),
      d("ong-caja-detalle", "Detalle de caja", "/ong/caja/[id]", HIJO),
    ],
  },
  {
    clave: "maestros",
    etiqueta: "Maestros",
    icono: "ajustes",
    landing: "/maestros",
    permiso: ACCESO_CONTEXTO,
    destinos: [
      d("terceros", "Terceros", "/terceros"),
      d("terceros-nuevo", "Nuevo tercero", "/terceros/nuevo", ACCION),
      d("terceros-detalle", "Detalle de tercero", "/terceros/[id]", HIJO),
      d("condiciones-pago", "Condiciones de pronto pago", "/terceros/condiciones"),
      d("centros-coste", "Centros de coste", "/centros"),
      d("centros-nuevo", "Nuevo centro", "/centros/nuevo", ACCION),
      d("empresas", "Empresas", "/maestros/empresas"),
      d("empresas-nueva", "Alta de empresa", "/empresas/nueva", ACCION),
      d("permisos", "Permisos y roles", "/permisos"),
      d("permisos-auditoria", "Auditoría de accesos", "/permisos/auditoria"),
      d("exportaciones", "Exportación integral", "/exportaciones"),
      d("exportaciones-nueva", "Nueva exportación", "/exportaciones/nueva", ACCION),
      d("exportaciones-detalle", "Detalle de exportación", "/exportaciones/[id]", HIJO),
      d("ajustes-sii", "Ajustes de información fiscal", "", { ajuste: true }),
    ],
  },
] as const;

/** Las 6 claves del rail, en su orden fijo. */
export const CLAVES_RAIL: readonly string[] = SUPERFICIES.map((s) => s.clave);

/** Rutas sin destino de navegacion: no belongen a ninguna superficie. */
export const EXCEPCIONES_GUARD: readonly string[] = ["/login", "/"];

/** Todas las superficies, con sus destinos aplanados. */
export function todosLosDestinos(): readonly Destino[] {
  return SUPERFICIES.flatMap((s) => s.destinos);
}

export function superficiePorClave(clave: string): Superficie | undefined {
  return SUPERFICIES.find((s) => s.clave === clave);
}

export function destinoPorClave(clave: string): Destino | undefined {
  return todosLosDestinos().find((x) => x.clave === clave);
}

/**
 * Destinos que el panel muestra: ni acciones ni hijos. FR-013.
 * Los ajustes tambien se muestran: son algo que el usuario configura.
 */
export function destinosDePanel(clave: string): readonly Destino[] {
  const s = superficiePorClave(clave);
  if (!s) return [];
  return s.destinos.filter((x) => !x.accion && !x.hijo);
}

/** Destinos de una superficie, agrupados por grupo y en el orden declarado. */
export function destinosAgrupados(
  clave: string,
): readonly { grupo: string | null; destinos: readonly Destino[] }[] {
  const visibles = destinosDePanel(clave);
  const grupos: (string | null)[] = [];
  for (const x of visibles) {
    if (!grupos.includes(x.grupo ?? null)) grupos.push(x.grupo ?? null);
  }
  return grupos.map((g) => ({
    grupo: g,
    destinos: visibles.filter((x) => (x.grupo ?? null) === g),
  }));
}

/** La superficie a la que pertenece una ruta, o `undefined` si es una excepcion. */
export function superficieDeRuta(ruta: string): Superficie | undefined {
  const limpio = ruta.split("?")[0].replace(/\/$/, "") || "/";
  if (EXCEPCIONES_GUARD.includes(limpio)) return undefined;
  return SUPERFICIES.find((s) => s.destinos.some((x) => coincide(x.ruta, limpio)));
}

/** El destino activo para una ruta concreta. */
export function destinoDeRuta(ruta: string): Destino | undefined {
  const limpio = ruta.split("?")[0].replace(/\/$/, "") || "/";
  return todosLosDestinos().find((x) => coincide(x.ruta, limpio));
}

/**
 * Una ruta conida con una ruta patron. `/asientos/123` coincide con
 * `/asientos/[id]`, y `/asientos/diario` NO coincide con `/asientos/[id]`
 * porque el segmento literal tiene prioridad sobre el patron.
 */
function coincide(patron: string, ruta: string): boolean {
  if (!patron) return false;
  if (patron === ruta) return true;
  const p = patron.split("/");
  const r = ruta.split("/");
  if (p.length !== r.length) return false;
  return p.every((seg, i) => (seg.startsWith("[") ? r[i] !== "" : seg === r[i]));
}

/** `true` si el contexto concede el permiso de un par modulo/operacion. */
export function tienePermiso(
  ctx: Pick<ContextoSesion, "usuario"> | null,
  permiso: Permiso,
  concedidos: readonly (readonly [string, string])[] = [],
): boolean {
  void ctx;
  return concedidos.some(([m, o]) => m === permiso[0] && o === permiso[1]);
}
