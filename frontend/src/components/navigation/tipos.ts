/**
 * TIPOS COMPARTIDOS DE LA NAVEGACION (SPEC-031)
 *
 * Contratos con `GET /api/v1/contexto` y `GET /api/v1/favoritos`.
 * Los mirrors de los endpoints backend son:
 *   backend/src/services/navigation/contexto.py   (ContextoSesion)
 *   backend/src/services/navigation/favoritos.py  (Favorito)
 */

/** Estados derivados de un ejercicio. El mas restrictivo gana (research D4). */
export type EstadoEjercicio = "abierto" | "con_apertura" | "cerrado";

/** Un ejercicio de la empresa activa, tal y como lo devuelve el contexto. */
export interface EjercicioResuelto {
  ejercicio: number;
  estado: EstadoEjercicio;
  /** `ejercicio === anio en curso`. Regla explicita, no deducida. */
  es_actual: boolean;
  /** Asientos POSTED del ejercicio. Filtra siempre por empresa y por estado. */
  n_asientos: number;
  /** `false` si esta cerrado o no existe en ninguna de las dos fuentes. */
  es_seleccionable: boolean;
}

export interface UsuarioContexto {
  id: number;
  email: string;
  nombre: string;
  rol: string | null;
}

export interface EmpresaContexto {
  id: number;
  nombre: string;
  nif: string | null;
  es_activa: boolean;
}

/** Respuesta de `GET /api/v1/contexto`. */
export interface ContextoSesion {
  usuario: UsuarioContexto;
  empresa: EmpresaContexto;
  ejercicio_activo: EjercicioResuelto;
  ejercicios: EjercicioResuelto[];
}

/** Un favorito del usuario en la empresa activa. */
export interface Favorito {
  destino: string;
  orden: number;
  /** `false` si el destino existe pero el usuario perdio el permiso. */
  accesible: boolean;
  /** `true` si la clave ya no esta en el mapa: se ofrece retirarla. */
  desconocido?: boolean;
}

/** Respuesta de `GET /api/v1/favoritos`. */
export interface FavoritosRespuesta {
  items: Favorito[];
  /** Favoritos guardados. Puede superar `visibles`. */
  total: number;
  /** Los que el cliente muestra. Como maximo 5. */
  visibles: number;
}
