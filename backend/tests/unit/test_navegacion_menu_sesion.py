"""Invariantes del menu de sesion (correccion provisional 2026-09-29).

La zona de contexto de arriba mostraba empresa, ejercicio y usuario, pero el usuario
no tenia ninguna accion: no habia forma de **cerrar sesion** en ningun sitio de la
aplicacion. `SessionMenu.tsx` es ese sitio.

Estos tests leen el fuente, no ejecutan React (el proyecto no tiene runner de tests
de frontend, y anadir uno por tres reglas es mas de lo que se pide). Comprueban lo
que se puede comprobar leyendo:

1. Que el menu esta **montado** en la zona de contexto, en escritorio y en compacto.
   Un componente correcto que nadie monta no hace nada, y es el fallo mas caro de
   los tres: el fichero compila, `tsc` pasa, `next build` pasa.
2. Que el menu ofrece las tres acciones que se pidieron, con `role` de menu.
3. Que cerrar sesion hace lo que tiene que hacer, **y en este orden**: el ejercicio
   se borra antes que la empresa, porque `setEjercicioActivo(null)` solo puede
   borrar la entrada si todavia sabe de que empresa es.
4. Que el menu no reimplementa la presentacion del estado del ejercicio: reutiliza
   `etiqueta` y `clase` de `ExerciseSwitcher`. FR-031 dice que el estado no puede
   depender solo del color, y son dos funciones que se separan en cuanto una de las
   dos se toca.
"""

from __future__ import annotations

import re
from pathlib import Path

NAV = Path(__file__).resolve().parents[3] / "frontend" / "src" / "components" / "navigation"
MENU = NAV / "SessionMenu.tsx"
CONTEXTO = NAV / "ContextZone.tsx"
EJERCICIO = NAV / "SessionContext.tsx"
ALMACEN_EJERCICIO = NAV / "ejercicio.ts"
CLIENTE = Path(__file__).resolve().parents[3] / "frontend" / "src" / "services" / "client.ts"


def _texto(fichero: Path) -> str:
    return fichero.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. El menu esta montado
# ---------------------------------------------------------------------------


def test_el_menu_se_importa_en_la_zona_de_contexto() -> None:
    assert 'from "./SessionMenu"' in _texto(CONTEXTO)


def test_el_menu_se_monta() -> None:
    """Un componente correcto que nadie monta no hace nada, y nada lo delata."""
    texto = _texto(CONTEXTO)
    montajes = re.findall(r"<SessionMenu\b[^>]*>", texto)
    assert len(montajes) == 2, (
        "el menu tiene que estar en el escritorio y en la hoja de compacto, "
        f"y aparece {len(montajes)} veces"
    )


def test_el_menu_recibe_la_lista_de_empresas() -> None:
    """Sin la lista, "cambiar de empresa" no tendria nada que ofrecer."""
    for montaje in re.findall(r"<SessionMenu\b[^>]*/?>", _texto(CONTEXTO)):
        assert "empresas={" in montaje


# ---------------------------------------------------------------------------
# 2. Las tres acciones
# ---------------------------------------------------------------------------


def test_el_menu_ofrece_las_tres_acciones() -> None:
    texto = _texto(MENU)
    for accion in ("Cambiar de empresa", "Cambiar de ejercicio", "Cerrar sesi"):
        assert accion in texto, f"falta la accion {accion!r} en el menu de sesion"


def test_el_panel_es_un_menu_con_papel_de_menu() -> None:
    texto = _texto(MENU)
    assert 'role="menu"' in texto
    assert 'aria-haspopup="menu"' in texto
    assert 'aria-expanded={abierto}' in texto
    # Sin `aria-haspopup` ni `role`, un menu es una lista de palabras y un lector
    # de pantalla no anuncia que se ha abierto nada.
    assert texto.count('role="menuitem') >= 3


def test_el_menu_no_aparece_en_la_pantalla_de_identificacion() -> None:
    """`ContextZone` se suprime entero en `/login`; si el menu no hereda eso, se
    ve un boton de usuario en la pantalla donde todavia no hay usuario."""
    texto = _texto(CONTEXTO)
    corte = texto.index('if (pathname === "/login") return null;')
    assert corte < texto.index("<SessionMenu")


def test_el_disparador_muestra_quien_esta_dentro() -> None:
    """Sin el nombre en el propio boton, la accion solo se encuentra si se busca."""
    disparador = _texto(MENU)[_texto(MENU).index("<button") : _texto(MENU).index("</button>")]
    assert "usuario.nombre" in disparador


# ---------------------------------------------------------------------------
# 3. Cerrar sesion
# ---------------------------------------------------------------------------


def _cuerpo_de_salir() -> str:
    texto = _texto(MENU)
    inicio = texto.index("const salir")
    return texto[inicio : texto.index("\n  };", inicio)]


def test_cerrar_sesion_limpia_la_sesion_y_manda_a_identificarse() -> None:
    cuerpo = _cuerpo_de_salir()
    assert "limpiarSesion()" in cuerpo
    assert 'router.push("/login")' in cuerpo


def test_cerrar_sesion_borra_el_ejercicio_ANTES_de_la_empresa() -> None:
    """El orden no es cosmetico y ya se ha pagado en este proyecto.

    `limpiarSesion()` borra la empresa activa. `setEjercicioActivo(null)` solo puede
    borrar la entrada del mapa si todavia sabe de que empresa es. Al reves, el
    ejercicio elegido se queda en `localStorage` y el siguiente usuario de la misma
    maquina abre la aplicacion en el ejercicio que eligio el anterior.
    """
    cuerpo = _cuerpo_de_salir()
    assert cuerpo.index("setEjercicioActivo(null)") < cuerpo.index("limpiarSesion()")


def test_el_ejercicio_se_borra_por_empresa() -> None:
    """Si `setEjercicioActivo` se limitara a escribir un valor global, la cuenta
    seria otra: el almacen es un mapa `empresa -> ejercicio` (FR-004)."""
    almacen = _texto(ALMACEN_EJERCICIO)
    assert "delete mapa[empresa]" in almacen
    assert "ejercicio === null" in almacen


def test_limpiar_sesion_tambien_borra_la_cookie() -> None:
    """El token vive en dos sitios: `localStorage` (para el `fetch`) y una cookie
    httpOnly (para el middleware). Si el cierre no la borra, el middleware sigue
    viendo sesion y `/login` no es la primera pantalla."""
    cliente = _texto(CLIENTE)
    cuerpo = cliente[cliente.index("export function limpiarSesion") :]
    cuerpo = cuerpo[: cuerpo.index("\n}")]
    assert "setToken(null)" in cuerpo
    assert "eliminarCookieSesion()" in cuerpo


def test_el_middleware_sigue_viendo_una_sesion_inexistente() -> None:
    """El menu va a `/login` con `router.push`, que es una navegacion **de cliente**.
    Si el login se pide con el token de antes, lo que se ve es la pantalla de
    identificacion con la sesion viva; por eso `limpiarSesion` va antes del push."""
    cuerpo = _cuerpo_de_salir()
    assert cuerpo.index("limpiarSesion()") < cuerpo.index('router.push("/login")')


# ---------------------------------------------------------------------------
# 4. Lo que el menu delega y lo que no reimplementa
# ---------------------------------------------------------------------------


def test_el_menu_delega_el_cambio_en_el_contexto_de_sesion() -> None:
    """Cambiar de empresa o de ejercicio no se escribe aqui: se pide al almacen,
    que es quien sabe que hay que escribir ANTES de recargar."""
    texto = _texto(MENU)
    assert "cambiarEmpresa" in texto and "cambiarEjercicio" in texto
    assert "setEmpresaActiva" not in texto, "el menu no debe escribir el almacen de empresa"
    assert "setEjercicioActivo" in texto  # solo para el borrado del logout


def test_el_menu_reutiliza_la_presentacion_del_estado_del_ejercicio() -> None:
    """FR-031: el estado no puede depender solo del color. Si el menu se dibuja el
    estado por su cuenta, las dos copias se separan en cuanto una cambia."""
    menu = _texto(MENU)
    assert re.search(r'import\s*\{\s*clase,\s*etiqueta\s*\}\s*from\s*"\./ExerciseSwitcher"', menu)
    # Y no pinta el estado con su propia pinta: en la lista de ejercicios del menu
    # solo aparecen `clase(e)` y `etiqueta(e.estado, e.es_actual)`.
    bloque = menu[menu.index('aria-label="Ejercicio activo"') :]
    assert "clase(e)" in bloque
    assert "etiqueta(e.estado, e.es_actual)" in bloque


def test_la_etiqueta_de_estado_sigue_siendo_texto_y_no_solo_color() -> None:
    """`etiqueta` y `clase` estan en `ExerciseSwitcher` y el menu las importa: si
    alguien las vuelve a bajar al menu, estas dos dejan de ser la unica fuente."""
    selector = _texto(NAV / "ExerciseSwitcher.tsx")
    assert "export function etiqueta(" in selector
    assert "export function clase(" in selector
    assert re.search(r'if \(estado === "cerrado"\) return "cerrado";', selector)


def test_el_menu_marca_el_que_esta_activo() -> None:
    """Un menu donde no se ve cual de las dos empresas esta activa obliga a
    comprobarlo pulsando, que es el error que se queria evitar."""
    texto = _texto(MENU)
    assert 'aria-checked={activa}' in texto
    assert 'aria-checked={activo}' in texto


def test_un_ejercicio_cerrado_no_es_elegible_desde_el_menu() -> None:
    """El cerrado no admite asientos (SPEC-031). Si el menu lo deja marcar, el
    usuario elige un ejercicio donde no puede escribir y no se entera hasta fallar."""
    texto = _texto(MENU)
    assert "disabled={!e.es_seleccionable}" in texto
    assert "aria-disabled={!e.es_seleccionable}" in texto


def test_con_una_sola_empresa_el_menu_lo_dice() -> None:
    texto = _texto(MENU)
    assert "unaEmpresa" in texto
    assert "unica empresa a la que tienes acceso" in texto


def test_el_menu_se_cierra_al_pulsar_fuera_y_con_escape() -> None:
    """Sin esto el desplegable se queda pegado al cambiar de pagina y parece un
    fallo de la pantalla anterior."""
    texto = _texto(MENU)
    assert '"mousedown"' in texto
    assert '"Escape"' in texto


def test_los_selectores_rapidos_no_se_han_quitado() -> None:
    """El menu se **anade**: los dos selectores de la izquierda siguen montados,
    porque llevan el contador de asientos y el atajo al ejercicio anterior (FR-017)."""
    texto = _texto(CONTEXTO)
    assert "<CompanySwitcher empresas={empresas} />" in texto
    assert "<ExerciseSwitcher />" in texto
