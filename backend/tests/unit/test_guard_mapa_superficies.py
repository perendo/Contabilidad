"""Guard del mapa de superficies (SPEC-031, US2, tarea T022).

Con 103 pantallas, un mapa escrito a mano se desincroniza en semanas. Este test es
la red que convierte "una pantalla sin asignar" en un fallo de suite en vez de en
algo que se descubre cuando un usuario no encuentra una opcion.

COMO FUNCIONA: contrasta `frontend/src/components/navigation/surfaces.ts` contra las
pantallas reales del proyecto (`app/**/page.tsx`) en las dos direcciones:

1. Toda pantalla real esta en el mapa, en una redireccion, o es una excepcion.
2. Toda ruta declarada en el mapa existe de verdad, o esta en la lista de
   pendientes.

LA LISTA DE PENDIENTES Y POR QUE EXISTE

`PENDIENTES` son las rutas que el mapa declara y que todavia **no** existen porque
las crea una fase posterior: las 5 landings de superficie (US5) y el listado de
empresas (US5). Sin esta lista, el guard solo podria activarse al final de la
feature, y durante 40 tareas no comprobaria nada.

La lista **SOLO puede encogerse**. Si una ruta de `PENDIENTES` aparece ya en el
sistema, el test falla, porque eso significa que la fase que la crea ya ha
terminado y la lista no se ha limpiado. Una lista que miente deja de ser una red.
Es el mismo criterio que `test_guard_siembra_empresa.py` de la seccion 47 de
AGENTS.md.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

#: Raiz del REPOSITORIO, no de `backend/`. El fichero vive en
#: `backend/tests/unit/`, asi que `parents[2]` es `backend/` y el mapa esta en el
#: hermano `frontend/`. Es `parents[3]`.
RAIZ = Path(__file__).resolve().parents[3]
MAPA = RAIZ / "frontend" / "src" / "components" / "navigation" / "surfaces.ts"
APP = RAIZ / "frontend" / "src" / "app"

#: Rutas que el mapa declara y que crean fases posteriores. SOLO puede encogerse.
#:
#: **VACIA desde US6.** Contenia las 5 landings de superficie, el listado de empresas y la
#: canonica de import/export: las 7 se crearon y el guard obligo a limpiarla, que es
#: justo lo que un guard debe hacer. Se conserva el diccionario vacío y no se borra, con
#: su comentario, porque la siguiente fase que añada una pantalla con fases pendientes
#: tiene que volver a usar esta lista en vez de inventar otra.
PENDIENTES: dict[str, str] = {}

#: Direcciones que no tienen pantalla: un redirect de `next.config.mjs` las resuelve
#: antes del enrutado. Mismo criterio que las pendientes: solo se encoge.
#:
#: **SOLO `/contabilidad/import-export` desde la unificación de "nuevo asiento".** Antes
#: habia cinco y el diccionario mentia en cuatro de ellas: `/cierre`, `/cobros` y
#: `/tesoreria/efe` conservan su pantalla y estan en el mapa (US6 decidio no borrarlas,
#: ver `test_rutas_consolidadas`), y `/contabilidad/asientos/nuevo` **no tenia redirect
#: ninguno** — era una pantalla real fuera del mapa que este guard autorizaba diciendo
#: "canonica /asientos/nuevo". Se fusiono con la canonica y desaparecio. Por eso las dos
#: comprobaciones de mas abajo: una lista que no coincide con `next.config.mjs` deja de
#: ser una red y pasa a ser una puerta abierta.
REDIRIGIDAS: dict[str, str] = {
    "/contabilidad/import-export": "canonica /asientos/import-export",
}


def _leer_mapa() -> str:
    assert MAPA.exists(), f"falta el mapa de superficies: {MAPA}"
    return MAPA.read_text(encoding="utf-8")


def _rutas_reales() -> set[str]:
    reales: set[str] = set()
    for pagina in APP.glob("**/page.tsx"):
        rel = pagina.parent.relative_to(APP).as_posix()
        reales.add("/" if rel == "." else "/" + rel)
    return reales


def _entradas_mapa() -> list[tuple[str, str, str]]:
    r"""`(clave, etiqueta, ruta)` de cada `d(...)` declarado en el mapa.

    `\s*` tras `d(` es obligatorio: dos destinos (`cierre-ejercicio` e `informe-efe`)
    se declaran en varias lineas porque sus etiquetas son largas. Con la forma estricta
    `d("` el guard no los veia, y solo pasaban porque estaban en `REDIRIGIDAS`, es decir,
    la lista de redirecciones les tapaba la ausencia del mapa.
    """
    texto = _leer_mapa()
    return re.findall(r'd\(\s*"([^"]+)",\s*"([^"]*)",\s*"([^"]*)"', texto)


def _rutas_mapa() -> set[str]:
    """Rutas de destino, mas las landings de superficie.

    Se separa de las entradas para poder distinguir "destino mal formado" de
    "landing que no existe todavia".
    """
    texto = _leer_mapa()
    destinos = {ruta for _, _, ruta in _entradas_mapa() if ruta}
    landings = set(re.findall(r'landing:\s*"([^"]+)"', texto))
    return destinos | landings


def _excepciones() -> set[str]:
    texto = _leer_mapa()
    m = re.search(r"EXCEPCIONES_GUARD:[^=]*=\s*\[([^\]]*)\]", texto)
    assert m is not None, "el mapa debe declarar EXCEPCIONES_GUARD"
    return set(re.findall(r'"([^"]*)"', m.group(1)))


# ---------------------------------------------------------------------------
# 1. Toda pantalla real esta asignada
# ---------------------------------------------------------------------------


def test_toda_pantalla_real_esta_en_alguna_superficie() -> None:
    reales = _rutas_reales()
    conocidas = _rutas_mapa() | set(REDIRIGIDAS) | _excepciones()
    sin_asignar = sorted(reales - conocidas)
    assert sin_asignar == [], (
        "pantallas que no estan en el mapa, ni son redirect, ni excepcion:\n"
        + "\n".join(f"  {r}" for r in sin_asignar)
    )


def test_las_excepciones_son_las_declaradas_y_ninguna_mas() -> None:
    """La lista de excepciones no crece sin querer: es la puerta de la red.

    Si `EXCEPCIONES_GUARD` incluyera una pantalla de negocio, esa pantalla dejaria
    de estar cubierta por el guard sin que nadie se entere.
    """
    declaradas = _excepciones()
    reales = _rutas_reales()
    # `/` y `/login` si existen de verdad. Si una excepcion ya no esta, sobran.
    sobrantes = declaradas - reales
    assert sobrantes == set(), f"excepciones que ya no aplican: {sorted(sobrantes)}"
    # Ninguna ruta de negocio puede estar exenta.
    rutas_en_mapa = _rutas_mapa()
    assert declaradas.isdisjoint(rutas_en_mapa)


# ---------------------------------------------------------------------------
# 2. Toda ruta declarada existe
# ---------------------------------------------------------------------------


def test_toda_ruta_declarada_existe_o_esta_pendiente() -> None:
    reales = _rutas_reales()
    declaradas = _rutas_mapa()
    inexistentes = sorted(declaradas - reales)
    # Las landings de US5 son lo unico que se admite que aun no exista.
    admitidas = {r for r in inexistentes if r in PENDIENTES}
    sin_explicar = sorted(set(inexistentes) - admitidas)
    assert sin_explicar == [], (
        "rutas declaradas en el mapa que no existen y no estan en PENDIENTES:\n"
        + "\n".join(f"  {r}" for r in sin_explicar)
    )


def test_las_pendientes_solo_pueden_encogerse() -> None:
    """Si una ruta de `PENDIENTES` ya existe, la lista esta desfasada.

    Es el mismo principio de la red de siembra de empresas: una lista que miente
    deja de vigilar. Cuando US5 cree las landings, esta lista MUST vaciarse.
    """
    reales = _rutas_reales()
    ya_existentes = sorted(ruta for ruta in PENDIENTES if ruta in reales)
    assert ya_existentes == [], (
        "estas rutas de PENDIENTES ya existen: la fase que las crea termino y la "
        "lista no se ha limpiado\n" + "\n".join(f"  {r}" for r in ya_existentes)
    )


def test_las_pendientes_no_inventan_rutas() -> None:
    """La mitad inversa de la red: la lista no puede apuntar a rutas inventadas."""
    declaradas = _rutas_mapa()
    inventadas = sorted(ruta for ruta in PENDIENTES if ruta not in declaradas)
    assert inventadas == [], (
        "PENDIENTES apunta a rutas que el mapa no declara:\n"
        + "\n".join(f"  {r}" for r in inventadas)
    )


# ---------------------------------------------------------------------------
# 3. Coherencia interna del mapa
# ---------------------------------------------------------------------------


def test_las_claves_son_unicas() -> None:
    """La clave es lo que se guarda en `favorito_usuario`.

    Dos destinos con la misma clave harian que un favorito apuntase a dos cosas.
    """
    claves = [clave for clave, _, _ in _entradas_mapa()]
    repetidas = sorted({c for c in claves if claves.count(c) > 1})
    assert repetidas == [], f"claves de destino repetidas: {repetidas}"


def test_una_clave_no_se_deriva_de_su_ruta() -> None:
    """La clave se escribe a mano, nunca se deriva de la ruta (FR-026).

    Que hoy `catalogo` y `/catalogo` coincidan es una coincidencia de nombres, no
    una dependencia: si manana la ruta pasa a ser `/contabilidad/catalogo`, la clave
    sigue siendo `catalogo` y los favoritos guardados siguen resolviendo. Lo que si
    seria un defecto es que la clave se calculara, porque entonces cambiar la ruta
    cambiaria la clave y habria que migrar los favoritos de cada usuario.

    Por eso se comprueba que las claves sean ** literales**, y que exista al menos
    un destino cuya clave NO se parezca a su ruta, que es la prueba de que el mapa
    no esta haciendo la equivalencia.
    """
    entradas = _entradas_mapa()
    array = _array_superficies()
    # Espacio plano para poder comparar declaraciones escritas en varias lineas.
    plano = re.sub(r"\s+", " ", array)
    # Toda entrada se escribe como literal completo: `d("clave", "etiqueta", ...)`.
    # Un patron como `d("...", "..."` es justamente la forma buena, asi que lo que
    # se busca es la ausencia de las formas malas: plantilla, concatenacion, o una
    # llamada a una funcion.
    assert not re.search(r"d\(`", array), "alguna clave usa una plantilla"
    assert not re.search(r'd\(\s*"\s*"\s*[,)]', array), "hay una clave vacia"
    for clave, etiqueta, ruta in entradas:
        assert f'"{clave}", "{etiqueta}"' in plano, (
            f"la entrada {clave!r} no se escribe como literal en el array"
        )
        if ruta:
            assert f'"{ruta}"' in plano, (
                f"la ruta de {clave!r} no se escribe como literal"
            )
    # Prueba de que la separacion existe de verdad: al menos un destino cuya clave
    # difiere de su ruta normalizada. Si no hubiera ninguno, el mapa podria estar
    # derivando una de la otra sin que se notase.
    distintas = [
        clave
        for clave, _, ruta in entradas
        if ruta and clave != ruta.strip("/").replace("/", "-")
    ]
    assert distintas, (
        "ningun destino tiene clave distinta de su ruta: el mapa podria estar "
        "derivando una de la otra"
    )


def test_solo_los_ajustes_no_tienen_ruta() -> None:
    """Un ajuste vive en el panel; una ruta vacia en un destino seria un bug.

    Un destino con `ruta: ""` haria que `coincide("", ruta)` devolviera `True` para
    todo y el mapa trataria cada pantalla como ese destino.
    """
    sin_ruta = [clave for clave, _, ruta in _entradas_mapa() if not ruta]
    texto = _leer_mapa()
    for clave in sin_ruta:
        # Solo es valido si la misma entrada se declara como `ajuste`.
        patron = rf'd\("{re.escape(clave)}"[^)]*ajuste:\s*true'
        assert re.search(patron, texto), (
            f"destino {clave!r} sin ruta y sin `ajuste: true`"
        )


def test_hay_seis_superficies_y_son_las_declaradas() -> None:
    """El rail son 6, no mas ni menos (research D1: el rail admite de 3 a 7)."""
    texto = _leer_mapa()
    # Se filtran por el bloque de superficie, porque `clave` tambien aparece en los
    # destinos (que usan `d("clave", ...)`) y en las funciones de ayuda de mas abajo.
    superficies = re.findall(r'\{\s*\n\s*clave: "([a-z]+)",\s*\n\s*etiqueta:', texto)
    superficies = re.findall(r'\{\s*\n\s*clave: "([a-z]+)",\s*\n\s*etiqueta:', texto)
    assert superficies == [
        "contabilidad",
        "facturacion",
        "tesoreria",
        "informes",
        "fiscal",
        "maestros",
    ], f"superficies o su orden han cambiado: {superficies}"
    assert 3 <= len(superficies) <= 7, "fuera del rango que admite un rail de M3"


def test_cada_superficie_tiene_landing_y_al_menos_un_destino() -> None:
    """Ninguna superficie puede quedarse sin contenido.

    Una superficie con landing y cero destinos seria un boton que lleva a una pagina
    vacia, que es exactamente lo que el rail no debe tener.
    """
    bloques = _bloques_de_superficie()
    assert len(bloques) == 6, f"se esperaban 6 superficies, hay {len(bloques)}"
    for clave, bloque in bloques.items():
        assert re.search(r'landing:\s*"/', bloque), f"{clave} no declara landing"
        destinos = re.findall(r'd\("', bloque)
        assert destinos, f"{clave} no declara ningun destino"
        # Y al menos un destino de navegacion: acciones e hijos no cuentan.
        navegables = [
            d
            for d in re.findall(
                r'd\("([^"]+)",\s*"[^"]*",\s*"[^"]*"(,\s*\{[^}]*\})?', bloque
            )
            if d and "accion: true" not in (d[1] or "")
        ]
        assert navegables, f"{clave} no declara ningun destino navegable"


def _array_superficies() -> str:
    """El texto del array `SUPERFICIES`, y nada mas.

    Es obligatorio acotar: mas abajo del array hay funciones auxiliares que tambien
    contienen `clave:` y llamadas a `d(...)`, y parsear el fichero entero las
    confundia con superficies. Un parser ingenuo que aqui acierta por casualidad
    dejaria pasar una superficie sin comprobar.
    """
    texto = _leer_mapa()
    inicio = texto.index("SUPERFICIES: readonly Superficie[] = [")
    fin = texto.index("] as const;", inicio)
    return texto[inicio:fin]


def _bloques_de_superficie() -> dict[str, str]:
    """Un bloque por superficie, con su landing y sus destinos.

    Se parte por la apertura de cada elemento del array (`  {\n    clave: "..."`),
    que es el unico sitio donde una superficie empieza. La clave de la superficie va
    DESPUES de su `landing`, asi que el bloque se corta por la llave de entrada.
    """
    bloques: dict[str, str] = {}
    partes = re.split(r'\n  \{\n(?=\s*clave: ")', _array_superficies())
    for parte in partes[1:]:
        m = re.match(r'\s*clave:\s*"([a-z]+)"', parte)
        if m:
            bloques[m.group(1)] = parte
    return bloques


def test_toda_superficie_declara_un_destino_por_ejercicio() -> None:
    """Cada empresa tiene un solo ejercicio activo, pero todos deben poder verse.

    Se comprueba que el conjunto de destinos incluye los que el spec nombra como
    ciclo de vida del ejercicio (apertura, cierre, reaperturas), que es donde un
    error de mapeo seria mas facil.
    """
    claves = {clave for clave, _, _ in _entradas_mapa()}
    for obligatorio in ("apertura", "cierre-intermedio", "cierre-anual", "reaperturas"):
        assert obligatorio in claves, f"falta el destino {obligatorio!r}"


@pytest.mark.parametrize(
    "ruta",
    [
        "/contabilidad",
        "/facturacion",
        "/informes",
        "/fiscal",
        "/maestros",
    ],
)
def test_cada_superficie_tiene_su_landing_declarada(ruta: str) -> None:
    landings = set(re.findall(r'landing:\s*"([^"]+)"', _leer_mapa()))
    assert ruta in landings, f"la superficie {ruta} no declara su landing"


# ---------------------------------------------------------------------------
# 4. REDIRIGIDAS no miente
# ---------------------------------------------------------------------------


def _fuentes_redirect() -> set[str]:
    cfg = RAIZ / "frontend" / "next.config.mjs"
    assert cfg.exists(), f"falta next.config.mjs: {cfg}"
    return set(re.findall(r'source:\s*"([^"]+)"', cfg.read_text(encoding="utf-8")))


def test_toda_redirigida_tiene_un_redirect_de_verdad() -> None:
    """Una entrada de `REDIRIGIDAS` sin su `source:` en `next.config.mjs` es un falso.

    Esto es exactamente lo que pasaba con `/contabilidad/asientos/nuevo`: decia
    "canonica /asientos/nuevo" y no habia redirect ninguno, de modo que la pantalla
    seguia en el arbol fuera del mapa y el guard la daba por asignada. Una lista que
    miente deja de ser una red y pasa a ser una puerta abierta.
    """
    fuentes = _fuentes_redirect()
    sin_redirect = sorted(r for r in REDIRIGIDAS if r not in fuentes)
    assert sin_redirect == [], (
        "REDIRIGIDAS declara rutas sin redirect en next.config.mjs:\n"
        + "\n".join(f"  {r}" for r in sin_redirect)
    )


def test_las_redirigidas_no_tienen_pantalla() -> None:
    """La otra mitad: un redirect sobre una ruta que sigue teniendo pantalla no redirige."""
    reales = _rutas_reales()
    con_pantalla = sorted(r for r in REDIRIGIDAS if r in reales)
    assert con_pantalla == [], (
        "REDIRIGIDAS apunta a rutas que todavia tienen page.tsx:\n"
        + "\n".join(f"  {r}" for r in con_pantalla)
    )


def test_ningun_redirect_doble_con_una_pantalla() -> None:
    """Recorrido general: ninguna fuente de `next.config.mjs` conserva su pantalla.

    No solo las de `REDIRIGIDAS`: el fichero de configuracion es la fuente de verdad,
    y si se le añade un redirect sin borrar la pantalla, el usuario veria el formulario
    anterior un instante en lugar del 308.
    """
    reales = _rutas_reales()
    con_pantalla = sorted(f for f in _fuentes_redirect() if f in reales)
    assert con_pantalla == [], (
        "redirects cuya fuente todavia tiene pantalla:\n"
        + "\n".join(f"  {r}" for r in con_pantalla)
    )
