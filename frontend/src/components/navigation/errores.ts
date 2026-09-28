/**
 * TRADUCCION DE ERRORES DE EJERCICIO (SPEC-031, T036)
 *
 * El backend ya responde en castellano (`El ejercicio {anio} esta cerrado para la
 * empresa`). Lo que le falta a ese mensaje es la **accion**: el usuario lee que no
 * puede escribir, pero no que puede hacer para resolverlo. Y en este caso la accion
 * es obvia y no esta en ninguna parte: cambiar de ejercicio.
 *
 * Este modulo es el unico sitio donde se traduce un codigo de error a algo
 * accionable, y `test_errores_ejercicio.py` lo cruza con los codigos que el backend
 * puede emitir. Si el backend anade un codigo y nadie lo traduce aqui, ese test
 * falla: es la forma de que la capa de presentacion no se quede atras.
 *
 * NO se tocan los 103 pantalleros que ya hacen fetch: cada una muestra hoy el
 * `detail` del backend, que es correcto. Este modulo lo usan las queishments anaden
 * la accion, y quedara disponible para el resto sin obligar a refactorizarlas.
 */

import type { EjercicioResuelto } from "./tipos";

/** Que puede hacer el usuario, por codigo de error. */
export interface MensajeEjercicio {
  /** Texto para el usuario. Sin jerga y sin codigos. */
  texto: string;
  /** `true` si el problema se resuelve cambiando de ejercicio. */
  ofreceCambio: boolean;
}

export const MENSAJES: Record<string, MensajeEjercicio> = {
  ejercicio_cerrado: {
    texto: "Este ejercicio esta cerrado. Elige uno abierto para seguir contabilizando.",
    ofreceCambio: true,
  },
  ejercicio_no_pertenece_a_empresa: {
    texto: "Ese ejercicio no es de la empresa activa.",
    ofreceCambio: true,
  },
  ejercicio_invalido: {
    texto: "El ejercicio indicado no es valido.",
    ofreceCambio: true,
  },
  ejercicio_legalizado: {
    texto: "Este ejercicio esta legalizado y no admite nuevos asientos.",
    ofreceCambio: true,
  },
  periodo_cerrado: {
    texto: "El periodo al que pertenece la fecha esta cerrado.",
    ofreceCambio: false,
  },
};

/** `true` si el error se resuelve cambiando de ejercicio. */
export function esErrorDeEjercicio(code: string | undefined): boolean {
  return code !== undefined && code in MENSAJES;
}

/** Mensaje accionable, o `null` si el codigo no es de ejercicio. */
export function mensajeDeEjercicio(code: string | undefined): MensajeEjercicio | null {
  if (code === undefined) return null;
  return MENSAJES[code] ?? null;
}

/** Texto listo para mostrar, o `null`. */
export function textoDeEjercicio(code: string | undefined): string | null {
  return mensajeDeEjercicio(code)?.texto ?? null;
}

/**
 * Ejercicios a los que se puede saltar ahora mismo.
 *
 * Se ordena de mas reciente a mas antiguo, porque el caso habitual es cerrar el ano:
 * el usuario quiere el anterior, y el siguiente paso casi siempre es hacia atras.
 */
export function ejerciciosAbiertos(filas: readonly EjercicioResuelto[]): EjercicioResuelto[] {
  return filas
    .filter((e) => e.es_seleccionable)
    .slice()
    .sort((a, b) => b.ejercicio - a.ejercicio);
}

/** Texto del boton de recuperacion: "Pasar a 2026". */
export function etiquetaDeSalto(destino: EjercicioResuelto): string {
  return `Pasar a ${destino.ejercicio}`;
}
