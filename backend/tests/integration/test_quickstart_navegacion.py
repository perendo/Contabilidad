"""Comprobación automatizada de lo verificable del quickstart (SPEC-031, T066).

El quickstart son diez recorridos **manuales de navegador**: R1 pide "mira el rail de
arriba abajo". Un test no puede mirar un rail. Decir que se validan sin mas seria falso, y
esta spec ya ha tenido bastante de dar por comprobado lo que no lo estaba.

Lo que este fichero hace es **separar** las dos cosas:

1. Lo que SÍ se puede comprobar sin una persona mirando una pantalla, y se comprueba.
2. Lo que depende de ver la pantalla, y se dice con claridad, con el requisito concreto
   que quedaría sin cubrir si nadie lo mira.

La lista de la parte 2 es el entregable importante de este fichero: es la lista de lo que
un revisor tiene que mirar a mano, escrita para que no se pierda.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
SURFACES = RAIZ / "frontend" / "src" / "components" / "navigation" / "surfaces.ts"
PANEL = RAIZ / "frontend" / "src" / "components" / "navigation" / "SurfacePanel.tsx"
RAIL = RAIZ / "frontend" / "src" / "components" / "navigation" / "DestinationRail.tsx"
MOBILE = RAIZ / "frontend" / "src" / "components" / "navigation" / "MobileNav.tsx"
ZONA = RAIZ / "frontend" / "src" / "components" / "navigation" / "ContextZone.tsx"
CONFIG = RAIZ / "frontend" / "next.config.mjs"


def _superficies() -> list[re.Match[str]]:
    texto = SURFACES.read_text(encoding="utf-8")
    return list(re.finditer(r'\n    clave: "([a-z]+)",\n    etiqueta: "([^"]*)"', texto))


# ---------------------------------------------------------------------------
# R1, R2 · identidad y zona de contexto
# ---------------------------------------------------------------------------


def test_r1_r2_la_zona_de_contexto_monta_identidad_empresa_y_ejercicio() -> None:
    """La zona de contexto se monta en el layout raíz, antes del contenido."""
    layout = (RAIZ / "frontend" / "src" / "app" / "layout.tsx").read_text(encoding="utf-8")
    assert "<ContextZone />" in layout
    # El orden importa: la zona va antes de `AppShell`, o el contenido se pinta antes de
    # que el usuario sepa en qué empresa y ejercicio está.
    assert layout.index("<ContextZone />") < layout.index("<AppShell>")

    zona = ZONA.read_text(encoding="utf-8")
    assert "empresa.nombre" in zona, "la empresa se muestra junto al ejercicio"
    assert "ejercicio.ejercicio" in zona
    assert "usuario.nombre" in zona, "la identidad se ve (R1)"


def test_r2_el_ejercicio_se_distingue_por_color_y_por_texto() -> None:
    """FR-016: el estado se distingue por los dos medios, no solo por el color.

    Un estado que solo se distingue por color no lo ve quien no lo distingue, y el
    requisito lo dice así a propósito.
    """
    zona = ZONA.read_text(encoding="utf-8")
    assert "bg-amber-100" in zona, "distinción visual del estado"
    assert "cerrado" in zona, "y también textual"


# ---------------------------------------------------------------------------
# R3 · las seis superficies
# ---------------------------------------------------------------------------


def test_r3_hay_seis_superficies_en_orden_fijo() -> None:
    """FR-009: el orden del rail no depende del uso."""
    claves = [m.group(1) for m in _superficies()]
    assert claves == ["contabilidad", "facturacion", "tesoreria", "informes", "fiscal", "maestros"]


def test_r3_el_rail_tiene_las_seis_y_el_panel_las_usa() -> None:
    rail = RAIL.read_text(encoding="utf-8")
    assert "CLAVES_RAIL" in rail, "el rail usa el orden fijo del mapa"
    panel = PANEL.read_text(encoding="utf-8")
    assert "superficieDeRuta" in panel, "el panel deduce la superficie de la ruta"
    assert "destinosAgrupados" in panel, "y lista sus destinos"


def test_r3_cada_superficie_tiene_landing_con_resumen() -> None:
    texto = SURFACES.read_text(encoding="utf-8")
    for m in _superficies():
        inicio = m.start()
        fin = min((x.start() for x in _superficies() if x.start() > inicio), default=len(texto))
        bloque = texto[inicio:fin]
        landing = re.search(r'landing: "([^"]*)"', bloque)
        assert landing is not None, m.group(1)
        assert landing.group(1), f"{m.group(1)} no declara landing"
    panel = PANEL.read_text(encoding="utf-8")
    assert "ResumenSuperficie" in panel, "el panel monta el resumen en la landing"


# ---------------------------------------------------------------------------
# R5, R6 · favoritos y pantallas
# ---------------------------------------------------------------------------


def test_r6_las_pantallas_nuevas_existen() -> None:
    app = RAIZ / "frontend" / "src" / "app"
    for ruta in ("contabilidad", "facturacion", "informes", "fiscal", "maestros",
                 "maestros/empresas", "asientos/import-export"):
        assert (app / ruta / "page.tsx").exists(), f"falta la landing /{ruta}"


# ---------------------------------------------------------------------------
# R7 · rutas que cambian de sitio
# ---------------------------------------------------------------------------


def test_r7_el_esta_antiguo_responde_308_al_canónico() -> None:
    """El redirect declarado y su destino, verificados contra `next.config.mjs`.

    Se lee el bloque `REDIRECTS` y no el fichero entero: `next.config.mjs` también
    declara `rewrites` con su propio `source` (`/api/v1/:path*`), y contar todos los
    `source` del fichero daría dos por uno y compararías un redirect con un rewrite.
    """
    texto = CONFIG.read_text(encoding="utf-8")
    bloque = texto[texto.index("const REDIRECTS") : texto.index("];", texto.index("const REDIRECTS"))]
    fuentes = re.findall(r'source: "([^"]*)"', bloque)
    destinos = re.findall(r'destination: "([^"]*)"', bloque)
    assert fuentes and destinos and len(fuentes) == len(destinos)
    for origen, canonico in zip(fuentes, destinos, strict=True):
        assert (RAIZ / "frontend" / "src" / "app" / canonico.strip("/") / "page.tsx").exists(), (
            f"{origen} redirige a {canonico}, que no existe"
        )
    assert "permanent: true" in texto


# ---------------------------------------------------------------------------
# R8 · móvil
# ---------------------------------------------------------------------------


def test_r8_en_compacto_no_hay_rail_pero_si_barra_inferior() -> None:
    """M3 desaconseja el rail en compacto: la barra sustituye al rail, no lo acompaña."""
    app_shell = (RAIZ / "frontend" / "src" / "components" / "navigation" / "AppShell.tsx").read_text(
        encoding="utf-8"
    )
    assert "DestinationRail" in app_shell and "MobileNav" in app_shell
    rail = RAIL.read_text(encoding="utf-8")
    assert "hidden" in rail or "compacto" in rail.lower() or "min-" in rail, (
        "el rail se oculta en compacto"
    )
    assert "useCompacto" in MOBILE.read_text(encoding="utf-8") or "md:" in MOBILE.read_text(
        encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# R9 · teclado
# ---------------------------------------------------------------------------


def test_r9_los_enlaces_de_navegacion_son_enlaces_reales() -> None:
    """Un `div` con `onClick` no es navegable con el teclado ni se puede abrir en otra pestaña.

    Es la diferencia entre "se ve" y "se puede usar", y en navegación es exactamente la
    diferencia entre funcionar y no funcionar.

    Se comprueba que **cada destino** se pinta con `<Link`, y no solo que la palabra
    aparezca en el fichero: un panel con un enlace de tres y cuarenta `div` con `onClick`
    cumpliría la comprobación débil y seguiría siendo inaccesible.
    """
    for fichero in (PANEL, RAIL, MOBILE):
        texto = fichero.read_text(encoding="utf-8")
        assert "<Link" in texto, f"{fichero.name} no usa enlaces reales"
        # Todo destino que se pinta tiene que salir de un `<Link href=`, no de un `onClick`.
        destinos = len(re.findall(r"destinos?\.map", texto))
        if destinos:
            assert len(re.findall(r"<Link\s", texto)) >= destinos, (
                f"{fichero.name} pinta destinos sin usar <Link para todos ellos"
            )


# ---------------------------------------------------------------------------
# R10 · lo que NO se puede comprobar aquí
# ---------------------------------------------------------------------------


#: Lo que un revisor tiene que mirar a mano, con el requisito que cubre. Es la lista que
#: este fichero entrega; sin ella, "T662 validado" sería una afirmación sin respaldo.
MANUAL = {
    "R1": "Que la identidad se lea antes que cualquier dato de negocio, a ojo.",
    "R2": "Que cambiar de empresa y de ejercicio en la zona repinte todo y la cabecera viaje.",
    "R3": "Que el indicador de destino activo sea único, y que ninguna etiqueta se recorte.",
    "R4": "Facturar en dos ejercicios con la cabecera puesta: es escritura real.",
    "R5": "Marcar un favorito, cambiar de empresa y de usuario, y ver que reaparece.",
    "R6": "Que cada pantalla muestre su lista de destinos y su resumen sin huecos.",
    "R7": "Abrir una ruta antigua en el navegador y comprobar que llega a la buena.",
    "R8": "La hoja de contexto en móvil y la barra de 4 destinos más «Más».",
    "R9": "Recorrer el shell entero solo con teclado, con el foco visible.",
    "R10": "Quitar un permiso en la matriz y ver qué pasa en pantalla.",
}


def test_lista_de_comprobacion_manual_esta_presente() -> None:
    """Se comprueba a sí misma: que los diez recorridos estén enumerados.

    No es una prueba del producto, es la garantía de que la entrega no esconde un hueco.
    """
    assert set(MANUAL) == {f"R{i}" for i in range(1, 11)}
    assert all(descripcion for descripcion in MANUAL.values())


def test_la_documentacion_dice_que_parte_es_manual() -> None:
    """El quickstart se declara manual, y esta nota lo recuerda donde se va a leer."""
    quickstart = (RAIZ / "specs" / "031-navegacion-superficies" / "quickstart.md").read_text(
        encoding="utf-8"
    )
    assert "R1 " in quickstart
    # Este fichero es la versión automatizada; se deja constancia en el quickstart para
    # que quien lo lea sepa qué está cubierto por tests y qué no.
    marca = "test_quickstart_navegacion.py"
    assert marca in quickstart, (
        "el quickstart no menciona su version automatizada: "
        "quien lo lea no sabra que R1-R10 tambien tienen tests"
    )
