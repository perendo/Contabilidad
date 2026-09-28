"""Resolucion real del mapa de superficies (SPEC-031, correccion 2026-09-28).

POR QUE ESTE FICHERO EXISTE Y NO ES OTRO QUE LEE PROSA
------------------------------------------------------

La suite de SPEC-031 comprobo durante toda la feature que el mapa de superficies
**declaraba** lo correcto, nunca que la aplicacion **resolviera** lo correcto. Las
puertas que la spec acepta como sustituto de un test de frontend son `tsc`, ESLint y
`next build`, y las tres pasan con la navegacion rota:

- `tsc` comprueba tipos, y aqui no hay ningun tipo en juego.
- `next build` comprueba que las rutas compilan, no que la rejilla se pinte.
- Los tests de pytest que existian leian el fichero `surfaces.ts` con expresiones
  regulares, asi que un `if` invertido dentro de `superficieDeRuta` era invisible
  para todos ellos.

El resultado fue que `superficieDeRuta` no resolvia la landing de su propia
superficie, y **las seis pantallas de entrada al programa se quedaban sin nada**:
sin resumen, sin rejilla de destinos y con el aviso de "no pertenece a ninguna
superficie". El rail se veia perfecto. El programa, no.

QUE HACE ESTE FICHERO
---------------------

Compila `surfaces.ts` con el **tsc del propio proyecto** y evalua el mapa con
**node**, de modo que la prueba ejercita el codigo real y no una reimplementacion en
Python. Reimplementar `coincide` aqui seria inutil: el defecto esta en que la funcion
no llega a comparar la landing, y una copia en Python pasaria en verde mientras la
pantalla sigue rota.

Node ya es una dependencia dura del proyecto (`next build` no corre sin el), asi que
esto no anade ninguna. Si `tsc` o `node` no estuvieran, los tests se omiten con un
motivo explicito: es preferible omitir una comprobacion a aparentar que se hizo.

Lo que se comprueba son las cuatro cosas que la feature prometo:

1. La landing de cada superficie resuelve a ESA superficie. Sin esto, entrar por el
   rail no lleva a ningun sitio (defecto A).
2. La ruta de cada destino que el panel muestra resuelve a la superficie que lo
   declara, y no a otra.
3. Un destino sin ruta navegable no llega al panel (defecto B): un `href` vacio
   resuelve a la URL actual, o sea un enlace que no lleva a ninguna parte.
4. El mapa sigue siendo el que promete la spec: 6 superficies, el rail completo, los
   grupos de Tesoreria y las claves de destino que el backend cataloguea.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
MAPA_TS = RAIZ / "frontend" / "src" / "components" / "navigation" / "surfaces.ts"
FRONTEND = RAIZ / "frontend"
TSC = FRONTEND / "node_modules" / "typescript" / "bin" / "tsc"

#: Identificador de ejemplo para resolver los patrones `[id]`.
ID_EJEMPLO = "3f0b1d2c-0000-4000-8000-000000000000"

#: Sonda de evaluacion. Importa el mapa ya compilado y vuelca en JSON tanto la
#: forma del mapa como lo que el codigo real resuelve para cada ruta. Python no
#: interpreta nada: pregunta.
#:
#: Los dos marcadores se sustituyen por texto, no con `str.format`: el cuerpo es
#: JavaScript lleno de llaves y `format` las interpretaria como campos.
SONDA = """
import { pathToFileURL } from "node:url";
import {
  SUPERFICIES,
  superficieDeRuta,
  destinosDePanel,
  destinosAgrupados,
  enlaceDeDestino,
  CLAVES_RAIL,
  todosLosDestinos,
} from "__MODULO__";

const idEjemplo = "__ID__";

/** Rutas que la aplicacion puede encontrar: landings, destinos y sus variantes. */
function rutas() {
  const salida = new Set();
  for (const s of SUPERFICIES) {
    salida.add(s.landing);
    salida.add(s.landing + "/");
    salida.add(s.landing + "?ejercicio=2025");
    for (const d of s.destinos) {
      if (!d.ruta) continue;
      salida.add(d.ruta);
      if (d.ruta.includes("[id]")) salida.add(d.ruta.replace("[id]", idEjemplo));
    }
  }
  return [...salida];
}

const resueltas = {};
for (const r of rutas()) {
  const s = superficieDeRuta(r);
  resueltas[r] = s ? s.clave : null;
}

const panel = {};
const grupos = {};
const enlaces = {};
for (const s of SUPERFICIES) {
  panel[s.clave] = destinosDePanel(s.clave).map((d) => d.clave);
  grupos[s.clave] = destinosAgrupados(s.clave).map((g) => g.grupo);
  for (const d of destinosDePanel(s.clave)) {
    enlaces[s.clave + "/" + d.clave] = enlaceDeDestino(d, s);
  }
}

console.log(JSON.stringify({
  superficies: SUPERFICIES.map((s) => ({
    clave: s.clave,
    landing: s.landing,
    etiqueta: s.etiqueta,
    destinos: s.destinos.map((d) => ({
      clave: d.clave,
      ruta: d.ruta,
      accion: Boolean(d.accion),
      hijo: Boolean(d.hijo),
      ajuste: Boolean(d.ajuste),
      ancla: d.ancla === undefined ? null : d.ancla,
    })),
  })),
  rail: CLAVES_RAIL,
  panel,
  grupos,
  enlaces,
  resueltas,
  total: todosLosDestinos().length,
}));
"""


@pytest.fixture(scope="module")
def mapa() -> dict:
    """El mapa de superficies **ejecutado**, no leido."""
    node = shutil.which("node")
    if not node or not TSC.exists():
        pytest.skip("hace falta node y el tsc del proyecto para evaluar el mapa")

    destino = Path(os.environ.get("TEMP", ".")) / f"spec031-mapa-{uuid.uuid4().hex}"
    destino.mkdir(parents=True, exist_ok=True)
    try:
        # Se compila el fichero suelto, sin el tsconfig del proyecto: `surfaces.ts`
        # solo importa tipos (`import type`), que se borran al compilar, asi que no
        # hace falta arrastrar el arbol de modulos de Next.
        #
        # `node_modules/typescript/bin/tsc` es un `.js` con shebang, no un ejecutable:
        # en Windows lanzarlo directamente da `WinError 193`, asi que se invoca a
        # traves de node, que es como lo llama `npm run typecheck`.
        subprocess.run(
            [
                node,
                str(TSC),
                str(MAPA_TS),
                "--outDir",
                str(destino),
                "--module",
                "esnext",
                "--target",
                "es2022",
                "--moduleResolution",
                "bundler",
                "--skipLibCheck",
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        compilado = destino / "surfaces.js"
        if not compilado.exists():
            pytest.fail(f"tsc no genero {compilado.name}: revisa la salida de la compilacion")

        sonda = destino / "sonda.mjs"
        sonda.write_text(
            SONDA.replace("__MODULO__", path_to_file_url(compilado)).replace(
                "__ID__", ID_EJEMPLO
            ),
            encoding="utf-8",
        )
        salida = subprocess.run(
            [node, str(sonda)],
            check=True,
            capture_output=True,
            text=True,
            # Sin esto, node devuelve UTF-8 y Python lo lee en la codificacion del
            # sistema (cp1252 en Windows): los acentos de "Operacion" y "Prevision"
            # llegan rotos y el test falla por la codificacion, no por el mapa.
            encoding="utf-8",
        )
        return json.loads(salida.stdout)
    finally:
        shutil.rmtree(destino, ignore_errors=True)


def path_to_file_url(ruta: Path) -> str:
    return "file:///" + str(ruta).replace("\\", "/").lstrip("/")


def _resuelve(mapa: dict, ruta: str) -> str | None:
    """La clave de superficie que el codigo real devuelve para `ruta`."""
    return mapa["resueltas"].get(ruta)


def _destino(mapa: dict, clave_superficie: str, clave_destino: str) -> dict:
    s = next(x for x in mapa["superficies"] if x["clave"] == clave_superficie)
    return next(d for d in s["destinos"] if d["clave"] == clave_destino)


# ---------------------------------------------------------------------------
# 1. La landing de cada superficie resuelve a esa superficie  (defecto A)
# ---------------------------------------------------------------------------


def test_cada_landing_resuelve_a_su_propia_superficie(mapa: dict) -> None:
    """El fallo que dejo el programa sin navegacion.

    `superficieDeRuta` tiene que considerar la landing de la superficie ademas de sus
    destinos. Sin eso, entrar por el rail -que apunta a la landing- devuelve
    `undefined`, y el panel no pinta ni el resumen ni la rejilla: la pantalla se queda
    en el titulo que trae la pagina.
    """
    huerfanas = [
        f"{s['clave']} ({s['landing']})"
        for s in mapa["superficies"]
        if _resuelve(mapa, s["landing"]) != s["clave"]
    ]
    assert huerfanas == [], (
        "estas landings no resuelven a su propia superficie, asi que al entrar por el "
        f"rail no se pintan ni el resumen ni los destinos: {huerfanas}"
    )


def test_la_landing_tambien_se_limpia_de_query_y_barra_final(mapa: dict) -> None:
    """La comparacion de landing no puede ser literal y ya.

    Una landing llega con `?ejercicio=2025` o con barra final. Si el resolutor limpiara
    solo una de las dos formas, el mismo destino resolveria segun como se escriba la
    URL.
    """
    for s in mapa["superficies"]:
        for variante in (s["landing"], s["landing"] + "/", s["landing"] + "?ejercicio=2025"):
            assert _resuelve(mapa, variante) == s["clave"], (
                f"{variante!r} deberia resolver a {s['clave']!r} y resuelve a "
                f"{_resuelve(mapa, variante)!r}"
            )


def test_entrar_a_una_superficie_no_deja_solo_el_titulo(mapa: dict) -> None:
    """Ninguna superficie puede quedarse sin destino navegable en su landing.

    Es la formulacion de "se entra a la superficie y lo unico que hay es un titulo",
    que es exactamente lo que se vio.
    """
    sin_destinos = [s["clave"] for s in mapa["superficies"] if not mapa["panel"][s["clave"]]]
    assert sin_destinos == [], (
        f"estas superficies no muestran ningun destino en su panel: {sin_destinos}"
    )


# ---------------------------------------------------------------------------
# 2. Ninguna ruta se resuelve a una superficie equivocada
# ---------------------------------------------------------------------------


def test_los_destinos_del_panel_resuelven_a_su_superficie(mapa: dict) -> None:
    """Cada destino sigue estando dentro de la superficie que lo declara.

    El arreglo de la landing anade una busqueda mas al resolutor, y una busqueda mas
    puede robarle un caso a otra. Esto lo vigila.
    """
    robados: list[str] = []
    for s in mapa["superficies"]:
        for clave in mapa["panel"][s["clave"]]:
            d = _destino(mapa, s["clave"], clave)
            # Un ajuste no tiene ruta: se ancla dentro de la landing, y su resolucion
            # se comprueba en `test_los_ajustes_se_anclan_en_la_landing_de_su_superficie`.
            if d["ajuste"]:
                continue
            resuelta = _resuelve(mapa, d["ruta"])
            if resuelta != s["clave"]:
                robados.append(
                    f"{clave!r} ({d['ruta']}) declara {s['clave']!r} y resuelve a {resuelta!r}"
                )
    assert robados == [], f"destinos que no resuelven a su propia superficie: {robados}"


def test_una_ruta_no_puede_reclamarse_desde_dos_superficies(mapa: dict) -> None:
    """Regla de solapamiento: ninguna ruta se declara en dos superficies.

    Anadir la landing a la busqueda crea la posibilidad de solape, y hay que dejarla
    escrita antes de que aparezca.
    """
    duenas: dict[str, str] = {}
    choques: list[str] = []

    def reclamar(ruta: str, clave: str) -> None:
        if not ruta:
            return
        previa = duenas.get(ruta)
        if previa is not None and previa != clave:
            choques.append(f"{ruta} ({previa} y {clave})")
        duenas.setdefault(ruta, clave)

    for s in mapa["superficies"]:
        reclamar(s["landing"], s["clave"])
        for d in s["destinos"]:
            reclamar(d["ruta"], s["clave"])
    assert choques == [], f"rutas declaradas por dos superficies a la vez: {choques}"


def test_las_pantallas_de_detalle_resuelven_con_el_segmento_real(mapa: dict) -> None:
    """`/asientos/<uuid>` tiene que resolver a la misma superficie que su patron.

    Sin esto, una pantalla de detalle se quedaria fuera de la rejilla, que es el mismo
    fallo que la landing pero en la direccion contraria.
    """
    huerfanas: list[str] = []
    for s in mapa["superficies"]:
        for d in s["destinos"]:
            if "[id]" not in d["ruta"]:
                continue
            real = d["ruta"].replace("[id]", ID_EJEMPLO)
            if _resuelve(mapa, real) != s["clave"]:
                huerfanas.append(f"{real} -> {_resuelve(mapa, real)!r} (esperado {s['clave']!r})")
    assert huerfanas == [], f"pantallas de detalle fuera de su superficie: {huerfanas}"


# ---------------------------------------------------------------------------
# 3. Ningun destino del panel es un enlace al vacio  (defecto B)
# ---------------------------------------------------------------------------


def test_los_destinos_del_panel_tienen_ruta_navegable(mapa: dict) -> None:
    """Un destino sin ruta no puede salir del panel como enlace.

    Un `href` vacio resuelve a la URL actual: el enlace no lleva a ninguna parte y se
    presenta como si fuera un destino mas. Un ajuste se resuelve como **ancla dentro
    de la landing de su superficie**, y por eso queda excluido de esta comprobacion.
    """
    sin_ruta = [
        clave
        for s in mapa["superficies"]
        for clave in mapa["panel"][s["clave"]]
        if not _destino(mapa, s["clave"], clave)["ruta"].strip()
        and not _destino(mapa, s["clave"], clave)["ajuste"]
    ]
    assert sin_ruta == [], (
        f"destinos del panel sin ruta navegable (enlaces al vacio): {sin_ruta}"
    )


def test_los_ajustes_se_anclan_en_la_landing_de_su_superficie(mapa: dict) -> None:
    """Quitar el `href` vacio deja al ajuste sin destino si no se le da uno.

    El panel compone el ancla como `{landing}#{ancla}`, asi que ni el ancla ni la
    landing pueden estar vacios.
    """
    problemas: list[str] = []
    for s in mapa["superficies"]:
        for d in s["destinos"]:
            if not d["ajuste"]:
                continue
            if not (d["ancla"] or "").strip():
                problemas.append(f"{d['clave']}: no declara ancla, no se puede enlazar")
            if not s["landing"].strip():
                problemas.append(f"{d['clave']}: su superficie {s['clave']} no tiene landing")
    assert problemas == [], problemas


def test_el_ancla_de_un_ajuste_existe_en_la_pagina_de_destino(mapa: dict) -> None:
    """El `id` que el panel enlaza tiene que existir en la landing.

    Es la mitad que hace util la anterior. Declarar el ancla en el mapa no sirve de
    nada si la pagina monta la seccion con otro `id`: el enlace seguiria llevando a la
    pagina, pero sin desplazarse a la seccion, y a ojo no se distingue de un enlace
    que funciona. Se comprueba en las dos mitades porque estan en ficheros distintos y
    basta con tocar una para que la otra vuelva a mentir.
    """
    rotos: list[str] = []
    for s in mapa["superficies"]:
        pagina = RAIZ / "frontend" / "src" / "app" / s["landing"].strip("/") / "page.tsx"
        if not pagina.exists():
            rotos.append(f"{s['clave']}: la landing {s['landing']} no tiene pagina")
            continue
        fuente = pagina.read_text(encoding="utf-8")
        for d in s["destinos"]:
            if not d["ajuste"]:
                continue
            ancla = d["ancla"] or d["clave"]
            if f'id="{ancla}"' not in fuente:
                rotos.append(
                    f"{d['clave']}: {pagina.relative_to(RAIZ)} no monta id=\"{ancla}\""
                )
    assert rotos == [], f"anclas de ajuste que no existen en su pagina: {rotos}"


def test_ningun_destino_del_panel_produce_un_enlace_al_vacio(mapa: dict) -> None:
    """Ninguna entrada del panel puede acabar en un `href` vacio o en la pagina misma.

    Se comprueba sobre lo que devuelve `enlaceDeDestino`, que es lo que el panel pasa
    a `Link`. Un enlace vacio resuelve a la URL actual: no lleva a ninguna parte y se
    presenta igual que los de verdad, que es la forma mas dificil de detectar a ojo.
    """
    vacios = [
        clave
        for clave, enlace in mapa["enlaces"].items()
        if enlace is None or enlace.strip() == ""
    ]
    assert vacios == [], f"entradas del panel sin enlace utilizable: {vacios}"


def test_los_ajustes_se_enlazan_con_un_ancla_de_su_propia_superficie(mapa: dict) -> None:
    """El enlace de un ajuste tiene que ser `{landing}#{ancla}` de su superficie.

    Y no `{landing}` a secas: un enlace a la propia pagina sin ancla no se distingue de
    uno que funciona, porque se llega igual.
    """
    for s in mapa["superficies"]:
        for d in s["destinos"]:
            if not d["ajuste"]:
                continue
            enlace = mapa["enlaces"][f"{s['clave']}/{d['clave']}"]
            esperado = f"{s['landing']}#{d['ancla'] or d['clave']}"
            assert enlace == esperado, (
                f"el ajuste {d['clave']!r} deberia enlazar a {esperado!r} y enlaza a {enlace!r}"
            )


def test_los_destinos_de_trabajo_enlazan_a_su_propia_ruta(mapa: dict) -> None:
    """Un destino normal enlaza a su ruta, sin ancla ni transformation.

    Es la contraparte del caso anterior: si `enlaceDeDestino` tocara cualquier cosa,
    seria para los 100 destinos de trabajo, no solo para el ajuste.
    """
    rarezas: list[str] = []
    for s in mapa["superficies"]:
        for clave in mapa["panel"][s["clave"]]:
            d = _destino(mapa, s["clave"], clave)
            if d["ajuste"]:
                continue
            enlace = mapa["enlaces"][f"{s['clave']}/{clave}"]
            if enlace != d["ruta"]:
                rarezas.append(f"{clave!r}: ruta {d['ruta']!r}, enlace {enlace!r}")
    assert rarezas == [], f"destinos que no enlazan a su propia ruta: {rarezas}"


def test_el_ajuste_de_informacion_fiscal_sigue_en_el_panel(mapa: dict) -> None:
    """Corregir el enlace vacio no puede consistir en quitar el ajuste del panel.

    El ajuste de informacion fiscal es FR-029. Si desaparece, la correccion habria
    silenciado un requisito en vez de cumplirlo.
    """
    ajustes = [d["clave"] for s in mapa["superficies"] for d in s["destinos"] if d["ajuste"]]
    assert ajustes == ["ajustes-sii"], (
        f"se esperaba solo el ajuste de informacion fiscal y hay: {ajustes}"
    )
    assert "ajustes-sii" in mapa["panel"]["maestros"], (
        "el ajuste de informacion fiscal ha desaparecido del panel de Maestros (FR-029)"
    )


# ---------------------------------------------------------------------------
# 4. El mapa sigue siendo el que promete la spec
# ---------------------------------------------------------------------------


def test_el_rail_sigue_teniendo_seis_destinos(mapa: dict) -> None:
    assert len(mapa["rail"]) == 6, f"el rail declara {len(mapa['rail'])} superficies"


def test_las_seis_superficies_siguen_siendo_las_seis(mapa: dict) -> None:
    assert [s["clave"] for s in mapa["superficies"]] == [
        "contabilidad",
        "facturacion",
        "tesoreria",
        "informes",
        "fiscal",
        "maestros",
    ]


def test_los_destinos_de_trabajo_no_se_han_perdido(mapa: dict) -> None:
    """El arreglo de la landing no puede haber perdido destinos por el camino.

    Se comparan contra la cuenta que declaraba el backend, `DESTINOS` de
    `services/navigation/destinos.py`, que es la copia de verificacion de
    `test_destinos_en_sync.py`. Si los dos se movieran a la vez, este test lo veria.
    """
    declarados = {
        d["clave"] for s in mapa["superficies"] for d in s["destinos"] if not d["ajuste"]
    }
    backend = _claves_del_backend()
    if backend is None:
        pytest.skip("no se encuentra services/navigation/destinos.py")
    assert declarados == backend, (
        "el mapa del frontend y el catalogo del backend ya no declaran lo mismo: "
        f"solo en frontend {sorted(declarados - backend)}, "
        f"solo en backend {sorted(backend - declarados)}"
    )


def test_el_panel_usa_el_enlace_que_resuelve_el_mapa() -> None:
    """El panel no puede volver a enlazar con `destino.ruta` a pelo.

    Sin esto, la correccion del enlace al vacio vive solo en `enlaceDeDestino`: quien
    tocara `SurfacePanel` para volver a poner `href={destino.ruta}` rehabilitaria el
    `href=""`, y los tests de arriba seguirian en verde porque la seguirian mirando
    solo la funcion, no lo que el panel hace con ella. Un guard que vigila la funcion
    nueva no vigia que la usen.
    """
    panel = (
        RAIZ / "frontend" / "src" / "components" / "navigation" / "SurfacePanel.tsx"
    ).read_text(encoding="utf-8")
    assert "enlaceDeDestino" in panel, "el panel no usa la resolucion de enlaces del mapa"
    assert "href={destino.ruta}" not in panel, (
        "el panel ha vuelto a enlazar con la ruta en crudo, que para un ajuste es un "
        "href vacio"
    )


def test_los_grupos_de_tesoreria_se_siguen_calculando(mapa: dict) -> None:
    """El agrupado del panel es lo que convierte la rejilla en secciones legibles."""
    grupos = mapa["grupos"]["tesoreria"]
    assert None in grupos, "tesoreria deberia conservar el grupo general sin nombre"
    faltan = {"Operación", "Instrumentos", "Banco", "Previsión"} - set(grupos)
    assert faltan == set(), f"faltan grupos en tesoreria: {sorted(faltan)}"


def _claves_del_backend() -> set[str] | None:
    """Las claves del catalogo `DESTINOS` del backend.

    Se importa el modulo de verdad en vez de parsearlo: el backend lo necesita para
    responder 404 a un favorito de una clave que no existe, asi que es una segunda
    declaracion del mismo mapa y tiene que contar lo mismo que la primera.
    """
    from services.navigation.destinos import DESTINOS

    return set(DESTINOS)


# ---------------------------------------------------------------------------
# 5. Los "ir a" del resumen tienen que llevar a una pantalla real  (defecto C)
# ---------------------------------------------------------------------------


def _enlaces_del_resumen() -> list[tuple[str, str]]:
    """Cada `_enlace(clave, etiqueta, ruta)` que declara el servicio de resumen."""
    import re

    servicio = RAIZ / "backend" / "src" / "services" / "navigation" / "resumenes.py"
    return [
        (clave, ruta)
        for clave, ruta in re.findall(
            r'_enlace\(\s*"([^"]+)",\s*"[^"]*",\s*"([^"]*)"\s*\)',
            servicio.read_text(encoding="utf-8"),
        )
    ]


def test_los_ir_a_del_resumen_apuntan_a_una_pantalla_que_existe() -> None:
    """Cada "ir a" del resumen tiene que tener una `page.tsx` detras.

    Estos enlaces los escribe el backend a mano, en un fichero que ninguna puerta
    contrasta con el arbol de pantallas del frontend. Cuatro de los trece apuntaban a
    rutas que no existen, osea un 404, y el quinto a una que existia pero estaba fuera
    del mapa de superficies. El resumen es lo que convierte una landing en util, asi
    que un "ir a" roto ahi se nota en la primera pantalla que se abre.
    """
    rotas = [
        ruta
        for _clave, ruta in _enlaces_del_resumen()
        if not (RAIZ / "frontend" / "src" / "app" / ruta.strip("/") / "page.tsx").exists()
    ]
    assert rotas == [], f"enlaces del resumen que no llevan a ninguna pantalla: {rotas}"


def test_los_ir_a_del_resumen_caen_en_alguna_superficie(mapa: dict) -> None:
    """Y ademas tienen que caer en una superficie, no en una pantalla huerfana.

    Es la segunda mitad del defecto: `/contabilidad/asientos/nuevo` **si** existia
    como pagina, y por eso un guard de "la ruta existe" no lo habria pillado. Abria
    una pantalla sin rejilla de destinos y con el aviso de que no pertenece a ninguna
    superficie, que es el mismo sintoma que la landing sin resolver.
    """
    huerfanas = [ruta for _clave, ruta in _enlaces_del_resumen() if _resuelve(mapa, ruta) is None]
    assert huerfanas == [], f"enlaces del resumen que caen fuera de toda superficie: {huerfanas}"


def test_el_resumen_declara_un_ir_a_por_superficie(mapa: dict) -> None:
    """Comprobacion de recuento: sin esto, los dos tests de arriba pasan con cero.

    Un resumen sin "ir a" informa pero no ayuda, que es justo lo que dice la
    docstring de `_enlace`: el usuario lee que le faltan cuatro facturas y tiene que
    acordarse de donde se emiten.
    """
    declaradas = {ruta for _clave, ruta in _enlaces_del_resumen()}
    sin_ir_a: list[str] = []
    for s in mapa["superficies"]:
        propias = {d["ruta"] for d in s["destinos"] if d["ruta"]}
        if not declaradas & (propias | {s["landing"]}):
            sin_ir_a.append(s["clave"])
    assert sin_ir_a == [], f"superficies cuyo resumen no ofrece ningun 'ir a': {sin_ir_a}"
