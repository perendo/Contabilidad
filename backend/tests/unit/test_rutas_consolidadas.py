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

EL SEGUNDO CONSOLIDADO: "Nuevo asiento"
---------------------------------------

SPEC-002 y SPEC-006 dejaron **dos** pantallas de alta de asientos con el mismo aspecto y
destinos distintos:

| Ruta | Formulario | Endpoint | ¿En el mapa? |
|---|---|---|---|
| `/asientos/nuevo` | `JournalEntryForm` (SPEC-001) | `POST /journal/entries` → **DRAFT** | sí, es la canónica |
| `/contabilidad/asientos/nuevo` | `LineEditor` (SPEC-006) | `POST /asientos` → **POSTED** | **no**, y sin redirect |

El síntoma en producción era directo: un asiento creado desde la navegación **no aparecía
en el libro diario**, que solo lista `POSTED`/`CANCELLED` por contrato histórico. La ruta
fuera del mapa estaba además autorizada por `REDIRIGIDAS`, que decía "canónica
/asientos/nuevo" sin que hubiera redirect ninguno: una lista que miente deja de ser una red.

Decisión: una sola pantalla en la canónica, con `LineEditor` y dos acciones —
**Asentar** (`POST /api/v1/asientos`, asienta de una vez) y **Guardar borrador**
(`POST /api/v1/journal/entries`). Se conserva la vía borrador porque la baja lógica de
documentos solo se admite sobre `DRAFT` (SPEC-030, FR-010) y porque los borradores ya
existentes tienen que poder asentarse desde la app: ahora, con el filtro de estado del
diario, se ven y se asientan.

Las 4-8 de mas abajo fijan esa decisión.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
APP = RAIZ / "frontend" / "src" / "app"
CONFIG = RAIZ / "frontend" / "next.config.mjs"
SUPERFICIES = RAIZ / "frontend" / "src" / "components" / "navigation" / "surfaces.ts"
NUEVO_ASIENTO = APP / "asientos" / "nuevo" / "page.tsx"

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


# ---------------------------------------------------------------------------
# 4. "Nuevo asiento" es una sola pantalla
# ---------------------------------------------------------------------------


def _paginas_de_alta_de_asientos() -> list[str]:
    """Rutas cuyo `page.tsx` **crea** un asiento (POST a la raíz del recurso).

    El patrón exige la comilla que cierra la cadena justo después del recurso, así que
    `POST .../reverse`, `.../post` o `.../importar/confirmar` no cuentan: son acciones
    sobre un asiento ya creado o sobre un fichero. También se pide que haya un `post`,
    para que un `page.tsx` que solo LEA `/api/v1/asientos` (el diario, el detalle) no
    salga aquí.
    """
    altas: list[str] = []
    for pagina in APP.glob("**/page.tsx"):
        texto = pagina.read_text(encoding="utf-8")
        if "post" not in texto:
            continue
        crea_en = ('"/api/v1/asientos"', '"/api/v1/journal/entries"')
        if any(ruta in texto for ruta in crea_en):
            rel = pagina.parent.relative_to(APP).as_posix()
            altas.append("/" + rel)
    return sorted(altas)


def test_hay_una_sola_pantalla_de_alta_de_asientos() -> None:
    """La que estaba en el mapa y la que no, fusionadas en una.

    Mientras existan dos, vuelve el defecto: una de ellas crea borradores que el libro
    diario no enseña, y ninguna de las dos es obviamente la correcta para quien llega
    por la navegación.
    """
    assert _paginas_de_alta_de_asientos() == ["/asientos/nuevo"]


def test_la_pantalla_de_borrador_de_contabilidad_ya_no_existe() -> None:
    """La ruta fuera del mapa se borró, no se vació ni se dejó un redirect.

    `next.config.mjs` no tiene ningún redirect con esa fuente: si la ruta sigue en el
    árbol, es una pantalla duplicada sirviendo a la vez.
    """
    assert not _existe("/contabilidad/asientos/nuevo")
    assert 'source: "/contabilidad/asientos/nuevo"' not in CONFIG.read_text(
        encoding="utf-8"
    )


def test_la_pantalla_unificada_tiene_las_dos_acciones() -> None:
    """Asentar y guardar borrador, las dos en la misma pantalla.

    Si una de las dos desaparece, hay que volver a la decisión anterior: o se asienta
    directo (y no se pueden rectificar los borradores con documentos) o solo se guardan
    borradores (y un asiento creado desde la app no sale en el diario).
    """
    texto = NUEVO_ASIENTO.read_text(encoding="utf-8")
    assert '"/api/v1/asientos"' in texto, "falta la accion Asentar"
    assert '"/api/v1/journal/entries"' in texto, "falta la accion Guardar borrador"
    assert "asentar" in texto and "guardarBorrador" in texto
