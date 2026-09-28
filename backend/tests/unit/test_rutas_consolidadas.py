"""Consolidación de rutas (SPEC-031, US6, T054).

Este test fija la decisión que se tomó sobre las cinco rutas, y sobre todo **por qué** no
se hizo lo que pedía la tarea.

LA TAREA DECÍA UNA COSA Y LOS FICHEROS DECÍAN OTRA
---------------------------------------------------

T055 pedía cinco redirects y T057 borrar cinco pantallas. Al abrir cada una resultó que
cuatro no eran duplicados: cada una tenía una función que su destino canónico no tiene.

| Ruta antigua | Función única que se habría perdido |
|---|---|
| `/cierre` | botón "Cerrar" sobre `fiscal-years/{year}/close` (SPEC-004) |
| `/cobros` | listado de cobros registrados contra un vencimiento |
| `/tesoreria/efe` | botón "Formular" del informe de flujos de efectivo (SPEC-027) |

Y un hallazgo aparte: **`/tesoreria/efe` no estaba en el mapa**. Nadie podía llegar a
ella. Eso no es "tener dos rutas parecidas", es una función entera fuera de la
navegación, y es un defecto peor que el que T057 quería arreglar.

DECISIÓN
--------

Solo se mueve lo que es realmente duplicado (import y export, que era el mismo código en
dos sitios), y las otras tres se conservan y se **añaden al mapa**. Es lo que hay que
comprobar aquí:

1. El único redirect declarado tiene su canónico en el árbol.
2. La pantalla movida ya no está en la ruta antigua.
3. Las tres conservadas existen **y** están en el mapa. Una pantalla que existe pero no
   está en el mapa es lo que se acaba de arreglar, así que el test vigila que no vuelva.
4. Ninguna ruta del mapa apunta a un fichero inexistente.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
APP = RAIZ / "frontend" / "src" / "app"
CONFIG = RAIZ / "frontend" / "next.config.mjs"
SUPERFICIES = RAIZ / "frontend" / "src" / "components" / "navigation" / "surfaces.ts"

PATRON_DESTINO = re.compile(r'd\(\s*"([a-z0-9_-]+)"\s*,\s*"([^"]*)"\s*,\s*"([^"]*)"')


def _rutas_del_mapa() -> list[tuple[str, str, str]]:
    return [
        (m.group(1), m.group(2), m.group(3))
        for m in PATRON_DESTINO.finditer(SUPERFICIES.read_text(encoding="utf-8"))
    ]


def _existe(ruta: str) -> bool:
    limpio = ruta.strip("/")
    return (APP / limpio / "page.tsx").exists() if limpio else (APP / "page.tsx").exists()


# ---------------------------------------------------------------------------
# 1. El redirect
# ---------------------------------------------------------------------------


def test_el_redirect_de_import_export_esta_declarado() -> None:
    texto = CONFIG.read_text(encoding="utf-8")
    assert 'source: "/contabilidad/import-export"' in texto
    assert 'destination: "/asientos/import-export"' in texto
    assert "permanent: true" in texto, "un cambio de ubicacion permanente es 308"


def test_el_canonico_del_redirect_existe() -> None:
    assert _existe("/asientos/import-export")


def test_la_ruta_antigua_ya_no_tiene_pantalla() -> None:
    """La pantalla se movió, no se copió.

    Si volviera a existir, habría dos rutas sirviendo el mismo formulario de importación,
    y solo una tendría los imports corregidos: la otra fallaría al buscar sus tres
    niveles de imports relativos.
    """
    assert not _existe("/contabilidad/import-export")


# ---------------------------------------------------------------------------
# 2. Las tres conservadas, que sí están en el mapa
# ---------------------------------------------------------------------------

#: (ruta, clave que debe tener en el mapa, por qué se conserva)
CONSERVADAS = [
    ("/cierre", "cierre-ejercicio", "botón de cierre de ejercicio de SPEC-004"),
    ("/cobros", "cobros-detalle", "detalle de cobros por vencimiento"),
    ("/tesoreria/efe", "informe-efe", "botón de formular el informe de flujos de efectivo"),
]


def test_las_tres_pantallas_conservadas_siguen_en_el_arbol() -> None:
    for ruta, _clave, _motivo in CONSERVADAS:
        assert _existe(ruta), f"{ruta} se conserva y no puede desaparecer"


def test_las_tres_pantallas_conservadas_estan_en_el_mapa() -> None:
    """La parte que de verdad importa: existir no basta, hay que poder llegar.

    `/tesoreria/efe` estaba exactamente en ese estado antes: el fichero en su sitio y
    ninguna entrada en el mapa. Quien quisiera formular el informe de flujos de efectivo
    tenía que teclear la URL.
    """
    del_mapa = {clave: ruta for clave, _etiqueta, ruta in _rutas_del_mapa()}
    for ruta, clave, _motivo in CONSERVADAS:
        assert clave in del_mapa, f"{ruta} no está en el mapa y es inalcanzable"
        assert del_mapa[clave] == ruta, f"{clave} apunta a {del_mapa[clave]}, no a {ruta}"


def test_ninguna_ruta_del_mapa_apunta_a_un_fichero_inexistente() -> None:
    """La comprobación que `next build` no hace.

    `next build` valida que las páginas existentes compilen. No sabe que un destino del
    panel apunte a una ruta que no existe, y el síntoma es un 404 en cuanto el usuario
    pulsa ese destino. Con 101 destinos, basta uno para que la navegación parezca rota.
    """
    faltan = [
        (clave, ruta)
        for clave, _etiqueta, ruta in _rutas_del_mapa()
        if "[" not in ruta and not _existe(ruta)
    ]
    assert not faltan, f"destinos que apuntan a rutas inexistentes: {faltan}"


# ---------------------------------------------------------------------------
# 3. Etiquetas (FR-015, T058)
# ---------------------------------------------------------------------------


def test_ninguna_etiqueta_es_solo_un_codigo_de_modelo() -> None:
    """FR-015: un código de modelo no puede ser la única denominación.

    Se conserva el número, que es como todo el mundo llama a esos modelos, pero
    acompañado de lo que es. "Modelo 200" a secas obligaba a saber qué es el 200;
    "Modelo 200 de sociedades" no.
    """
    solo_codigo = [
        ruta
        for _clave, etiqueta, ruta in _rutas_del_mapa()
        if re.fullmatch(r"Modelo \d+", etiqueta)
    ]
    assert not solo_codigo, f"etiquetas que son solo un codigo de modelo: {solo_codigo}"


def test_ninguna_etiqueta_de_superficie_es_un_acronimo() -> None:
    """FR-015 nombra las superficies, y las seis son palabras corrientes."""
    texto = SUPERFICIES.read_text(encoding="utf-8")
    etiquetas = re.findall(r'\n    etiqueta: "([^"]*)"', texto)
    assert len(etiquetas) == 6, "son seis superficies, ni una más ni una menos"
    for etiqueta in etiquetas:
        assert re.fullmatch(r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+", etiqueta), (
            f"«{etiqueta}» no es una palabra corriente"
        )
