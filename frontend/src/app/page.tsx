import { redirect } from "next/navigation";

/**
 * RAIZ DEL PROGRAMA (SPEC-031, T029)
 *
 * Antes esta pagina era un volcado de 24 enlaces sueltos: la "navegacion" del
 * programa era una lista en la pantalla de inicio, sin jerarquia, sin agrupar y con
 * 79 de las 103 pantallas inalcanzables desde ella.
 *
 * Ahora la raiz **redirige** a la landing de la primera superficie. No se sustituye
 * por un indice de secciones porque el rail ya cumple ese papel, y duplicarlo seria
 * tener dos navegaciones que se desincronizan.
 *
 * `/` esta en `EXCEPCIONES_GUARD` del mapa de superficies: no pertenece a ninguna
 * superficie, igual que `/login`. El guard de mapa lo comprueba.
 */
export default function Home() {
  redirect("/contabilidad");
}
