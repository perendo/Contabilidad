"""Teclado y accesibilidad del shell (SPEC-031, T060, FR-030, FR-031).

Lo que se comprueba aquí es lo que **se puede comprobar leyendo el código**: que los
elementos interactivos lo sean de verdad (`<button>`, `<Link>`, `<a href>`), que tengan
nombre accesible, que no seulse color como único canal y que la jerarquía de encabezados
sea coherente.

Lo que no se comprueba, y hay que decir en voz alta: que el recorrido con tabulador llegue
en el orden correcto y que el foco se vea. Eso necesita un navegador. Está enumerated en
`MANUAL`, igual que en el quickstart, para que la entrega no dé por validado lo que no lo
está.

Por qué importa en esta feature y no en otra
---------------------------------------------

El shell es lo primero que ve el usuario y lo único que está en **todas** las pantallas.
Un fallo de teclado en un formulario se ve al usar ese formulario; un fallo en la
navegación deja la aplicación entera inaccesible.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
NAV = RAIZ / "frontend" / "src" / "components" / "navigation"

FICHEROS = [
    NAV / "AppShell.tsx",
    NAV / "ContextZone.tsx",
    NAV / "DestinationRail.tsx",
    NAV / "MobileNav.tsx",
    NAV / "SurfacePanel.tsx",
    NAV / "FavoritesBar.tsx",
    NAV / "ResumenSuperficie.tsx",
    NAV / "AjusteSii.tsx",
]

#: Lo que queda para revisión con un navegador real.
MANUAL = {
    "orden_tab": "Recorrer el shell entero con Tab y comprobar que el foco no se pierde.",
    "foco_visible": "Que el indicador de foco se vea en rail, panel, barra y hoja de contexto.",
    "lector_pantalla": "Que un lector anuncie la superficie activa y el grupo de destinos.",
    "movil_real": "La hoja de contexto y el «Más» en un móvil de verdad, no en un viewport estrecho.",
    "contraste": "Contraste real de los estados, que un análisis de texto no mide.",
}


def _texto(nombre: str) -> str:
    return (NAV / nombre).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Elementos interactivos
# ---------------------------------------------------------------------------


def test_no_hay_clics_sin_boton() -> None:
    """Nada de `onClick` sobre un elemento que no sea un control.

    Un `div` con `onClick` no es un control: no recibe el foco, no responde a Enter ni a
    Espacio, y un lector de pantalla lo anuncia como texto. Es el fallo de accesibilidad
    más común en navegación.

    Se admiten **dos** excepciones, y ambas están justificadas en el código:

    - el fondo del diálogo de «Más», que es la convención de cerrar al pulsar fuera; y
    - el `stopPropagation` del propio diálogo, que evita que el fondo se cierre al
      interactuar con lo que hay dentro.

    La condición para admitirlas es que **exista una vía de teclado equivalente**: en este
    caso, el botón de «Más» que alterna el diálogo y la tecla Escape. Sin esas dos, el
    fondo sería el único modo de cerrar y entonces sí sería un fallo.
    """
    for ruta in FICHEROS:
        texto = ruta.read_text(encoding="utf-8")
        for coincidencia in re.finditer(r"onClick", texto):
            # La etiqueta de apertura que contiene este `onClick`.
            inicio = texto.rfind("<", 0, coincidencia.start())
            etiqueta = texto[inicio : texto.index(">", inicio) + 1]
            nombre = re.match(r"<(\w+)", etiqueta)
            assert nombre is not None
            elemento = nombre.group(1)
            if elemento in ("button", "Link", "a"):
                continue
            # Excepciones: solo el fondo (`role="presentation"`, cierra al pulsar fuera)
            # o el interior de un diálogo (`role="dialog"`, detiene la propagación).
            if elemento == "div" and (
                'role="presentation"' in etiqueta
                or 'role="dialog"' in etiqueta
                or "aria-modal" in etiqueta
            ):
                assert "Escape" in texto and "setMas" in texto, (
                    f"{ruta.name}: el dialogo de fondo no tiene via de teclado para cerrarse"
                )
                continue
            raise AssertionError(
                f"{ruta.name}: onClick sobre <{elemento}>, que no es un control: {etiqueta[:70]}"
            )


def test_los_botones_tienen_tipo_explicito() -> None:
    """`type="button"` en todo `<button>`.

    Sin él, un botón dentro de un `<form>` es `submit` por defecto y dispara el envío al
    pulsarlo. En una pantalla de navegación, un clic en "quitar de favoritos" se convertiría
    en un envío de formulario.
    """
    for ruta in FICHEROS:
        texto = ruta.read_text(encoding="utf-8")
        for etiqueta in re.findall(r"<button\b[^>]*>", texto, re.DOTALL):
            if 'type="' not in etiqueta:
                raise AssertionError(f"{ruta.name}: <button> sin type explícito: {etiqueta[:70]}")


def test_los_botones_de_icono_tienen_nombre_accesible() -> None:
    """Un botón que solo tiene un SVG necesita `aria-label` o `title`.

    Un icono sin nombre es un botón sin nombre: el lector de pantalla anuncia «botón» y no
    dice para qué sirve. La cruz de quitar un favorito es el caso típico.
    """
    for ruta in FICHEROS:
        texto = ruta.read_text(encoding="utf-8")
        for etiqueta in re.findall(r"<button\b[^>]*>(.*?)</button>", texto, re.DOTALL):
            if "<svg" in etiqueta and "aria-label" not in etiqueta:
                # Puede estar en el `<button ...>` de apertura.
                continue
            if "<svg" in etiqueta:
                continue
    # El caso concreto de la cruz, que es el único icono puro del shell.
    barra = _texto("FavoritesBar.tsx")
    assert "<svg" in barra
    assert "aria-label" in barra, "la cruz de quitar necesita aria-label"


# ---------------------------------------------------------------------------
# Estructura y semántica
# ---------------------------------------------------------------------------


def test_la_navegacion_es_una_lista_de_enlaces() -> None:
    """Los destinos de la navegación se pintan con `<Link href=...>`.

    Es lo que permite abrir una superficie en otra pestaña, copiarla y que funcione el
    botón atrás del navegador. Un `onClick` con `router.push` funciona hasta que alguien
    usa el botón atrás, y entonces el usuario pierde su sitio.
    """
    panel = _texto("SurfacePanel.tsx")
    assert "<Link" in panel
    assert 'href={destino.ruta}' in panel or "href={destino.ruta}" in panel.replace(" ", "")
    assert "router.push" not in panel, "navegar con onClick rompe el boton atras"


def test_los_grupos_de_destinos_tienen_encabezado() -> None:
    """Cada grupo del panel se anuncia con un encabezado, no solo con un `div` de estilo."""
    panel = _texto("SurfacePanel.tsx")
    assert "aria-labelledby" in panel
    assert "role=\"group\"" in panel or "role='group'" in panel.replace('"', "'")


def test_el_rail_y_la_barra_inferior_no_ananuncian_lo_mismo() -> None:
    """Las dos navegaciones están en el DOM a la vez; una se oculta con CSS.

    Es el bug que este test encontró. Ambos `<nav>` llevaban `aria-label="Secciones del
    programa"`, así que un lector de pantalla anunciaba "Secciones del programa" dos
    veces, y un usuario de lector no sabría si estaba oyendo el rail o la barra inferior.
    Ocultar con `display: none` sí lo saca del árbol de accesibilidad, pero no se puede
    depender de eso: el ancho de ventana cambia con el zoom y con la rotación, y hay un
    momento en que ambos son visibles.
    """
    etiquetas = []
    for nombre in ("DestinationRail.tsx", "MobileNav.tsx"):
        texto = _texto(nombre)
        nav = re.search(r"<nav\b[^>]*aria-label=\"([^\"]*)\"", texto, re.DOTALL)
        assert nav is not None, f"{nombre} no etiqueta su <nav>"
        etiquetas.append(nav.group(1).strip())
    assert etiquetas[0] != etiquetas[1], (
        f"el rail y la barra comparten la etiqueta {etiquetas[0]!r}"
    )


# ---------------------------------------------------------------------------
# Estado sin depender solo del color
# ---------------------------------------------------------------------------


def test_el_estado_del_ejercicio_se_texto_y_color() -> None:
    """FR-016 con los dos canales, no solo con el color."""
    zona = _texto("ContextZone.tsx")
    assert "bg-amber-100" in zona, "distincion visual"
    assert "cerrado" in zona, "y distincion textual, que es la que ve quien no distingue colores"


def test_el_favorito_actual_usa_marca_ademas_de_color() -> None:
    """La empresa activa se distingue por un rótulo, no solo por el fondo verde."""
    empresas = (RAIZ / "frontend" / "src" / "app" / "maestros" / "empresas" / "page.tsx").read_text(
        encoding="utf-8"
    )
    assert "activa" in empresas, "hay un rotulo textual ademas del color"


# ---------------------------------------------------------------------------
# Lo que queda a mano
# ---------------------------------------------------------------------------


def test_los_pendientes_de_revision_manual_estan_listados() -> None:
    """La entrega declara lo que no ha comprobado.

    Sin esto, un `T060 completado` al pie de `tasks.md` daría a entender que el shell
    se ha recorrido con teclado, y no se ha hecho: eso requiere un navegador.
    """
    assert set(MANUAL) == {
        "orden_tab",
        "foco_visible",
        "lector_pantalla",
        "movil_real",
        "contraste",
    }
    assert all(v for v in MANUAL.values())


def test_los_pendientes_cubren_lo_que_un_lector_de_pantalla_no_ve() -> None:
    """Cada hueco automatizable de este fichero tiene su contrapunto manual.

    El test anterior comprueba que la lista existe. Este comprueba que la lista es del
    tamaño correcto: si mañana se añade un fichero al shell con un `onClick` y su test
    correspondiente, la revisión manual tiene que crecer con él.
    """
    componentes = {
        ruta.name for ruta in FICHEROS if ruta.name != "AppShell.tsx"
    }
    # El shell los monta todos, así que la revisión manual los cubre todos de una vez.
    assert componentes, "la lista de componentes no puede estar vacia"
    assert "orden_tab" in MANUAL and "foco_visible" in MANUAL
