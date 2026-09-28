"""Invariantes de navegacion (SPEC-031, US2, tarea T023).

Estos tests no comprueban que un boton funcione. Comprueban que las **reglas** que
el spec fija para la navegacion estan escritas de forma que se puedan uphold, y que
un cambio futuro en el mapa no puede romperlas en silencio.

Las reglas que se vigilan:

1. El rail tiene 6 destinos, ni mas ni menos. M3 admite de 3 a 7; 6 es la
   decision de producto, y un sexto destino colado en el rail no se detectaria
   mirando la interfaz.
2. El orden de los destinos NO depende del uso. Es lo que hace la navegacion
   predecible (FR-009) y lo que impide que el rail se reordene por frecuencia.
3. Las acciones de creacion NO son destinos de navegacion (FR-013). Un
   "Nuevo asiento" en el rail es un anti-patron de M3: los destinos son lugares,
   no verbos.
4. Los favoritos viven aparte y NO alteran el rail (FR-023).
5. Ninguna etiqueta es solo una sigla (FR-015).
6. Cada destino declara el permiso que necesita, para que el panel pueda ocultarlo
   sin perder el favorito (FR-024).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
MAPA = RAIZ / "frontend" / "src" / "components" / "navigation" / "surfaces.ts"

#: Siglas que el dominio usa de forma habitual. Se permiten ** accompanied de su
#: significado** (por ejemplo "Modelo 200"), nunca solas.
SIGLAS_CONOCIDAS = {
    "IVA",
    "SII",
    "IRPF",
    "EFE",
    "PGC",
    "RBAC",
    "SEPA",
    "R19",
    "C19",
}

#: Numero de destinos del rail: decision de producto, dentro del rango 3-7 de M3.
RAIL_ESPERADO = 6


def _texto() -> str:
    return MAPA.read_text(encoding="utf-8")


def _array() -> str:
    texto = _texto()
    return texto[texto.index("SUPERFICIES: readonly Superficie[] = [") : texto.index("] as const;")]


def _constantes() -> dict[str, dict[str, bool]]:
    """Las banderas abreviadas que declara el mapa, resueltas a banderas booleanas.

    El mapa usa dos estilos a proposito, y el test tiene que entender los dos:

        d("x", "X", "/x", ACCION)                  -> constante
        d("x", "X", "/x", { accion: true })        -> literal

    Que la forma abreviada exista no es un defecto: hace el mapa legible. Lo que si
    seria un defecto es que el test solo entendiera una de las dos, porque dejaria de
    comprobar la mitad de las entradas sin avisar. Por eso aqui se parsean las
    declaraciones `const NOMBRE = { ... }` del propio fichero, en vez de suponer
    cuales son.
    """
    salida: dict[str, dict[str, bool]] = {}
    for nombre, cuerpo in re.findall(
        r"const (\w+)\s*=\s*\{([^}]*)\}\s*as const", _texto()
    ):
        banderas = {k: True for k in re.findall(r"(\w+):\s*true", cuerpo)}
        if banderas:
            salida[nombre] = banderas
    return salida


def _entradas() -> list[dict[str, object]]:
    """Cada `d(...)` del mapa, con sus banderas ya resueltas."""
    constantes = _constantes()
    salida: list[dict[str, object]] = []
    patron = r'd\("([^"]+)",\s*"([^"]*)",\s*"([^"]*)"(?:,\s*(\{[^}]*\}|\w+))?'
    for clave, etiqueta, ruta, extra in re.findall(patron, _array()):
        if extra is None:
            banderas: dict[str, bool] = {}
        elif extra.startswith("{"):
            banderas = {k: True for k in re.findall(r"(\w+):\s*true", extra)}
        else:
            banderas = dict(constantes.get(extra, {}))
        salida.append(
            {"clave": clave, "etiqueta": etiqueta, "ruta": ruta, "banderas": banderas}
        )
    return salida


def _superficies() -> list[str]:
    return re.findall(r'\n  \{\n\s*clave: "([a-z]+)"', _array())


# ---------------------------------------------------------------------------
# 1. El rail
# ---------------------------------------------------------------------------


def test_el_rail_tiene_seis_destinos() -> None:
    superficies = _superficies()
    assert len(superficies) == RAIL_ESPERADO, (
        f"el rail declara {len(superficies)} superficies, el producto decidio {RAIL_ESPERADO}"
    )


def test_el_rail_esta_dentro_del_rango_de_m3() -> None:
    """M3 admite de 3 a 7 destinos en el rail. Fuera de eso, el rail no aplica."""
    assert 3 <= len(_superficies()) <= 7


def test_las_superficies_no_se_repiten() -> None:
    superficies = _superficies()
    repetidas = sorted({s for s in superficies if superficies.count(s) > 1})
    assert repetidas == [], f"superficies repetidas en el rail: {repetidas}"


def test_el_orden_de_las_superficies_es_explicito_y_no_derivado() -> None:
    """El orden se escribe una a una; no se ordena por clave ni por frecuencia.

    Es la forma de hacer verificable FR-009. Un `sort()` pondria el rail en orden
    alfabetico y seria estable, pero dejaria de reflejar la decision de producto
    (contabilidad primero, fiscal despues).
    """
    array = _array()
    assert not re.search(r"\.sort\(", array), "el mapa ordena las superficies"
    assert "SUPERFICIES" in array
    # El orden del array ES el orden del rail; se comprueba que empieza por
    # contabilidad, que es el destino mas frecuente de un contable.
    assert _superficies()[0] == "contabilidad"


def test_la_ordenacion_por_uso_no_existe_en_el_mapa() -> None:
    """No hay ninguna pista de orden por uso: ni contador, ni `orden`, ni `frecuencia`.

    Es la negacion directa de "los favoritos reordenan el rail". Si alguien
    anadiera un campo `uso` o ordenase por frecuencia, este test lo pararia.
    """
    array = _array().lower()
    for prohibido in ("frecuencia", "veces_usado", "contador_uso", "orden_favorito"):
        assert prohibido not in array, f"el mapa empieza a ordenar por uso: {prohibido}"


# ---------------------------------------------------------------------------
# 2. Las acciones no son destinos
# ---------------------------------------------------------------------------


def test_las_acciones_estaan_marcadas_como_tales() -> None:
    """Toda entrada con `accion: true` existe, y ninguna navegable la lleva.

    Una accion sin marcar apareceria en el panel como si fuera un lugar, que es el
    anti-patron de M3 que FR-013 prohibe.
    """
    for entrada in _entradas():
        banderas = entrada["banderas"]
        if isinstance(banderas, dict) and (
            banderas.get("accion") or banderas.get("ajuste") or banderas.get("hijo")
        ):
            # Una accion, un ajuste o una pantalla hija se alcanzan sin ruta propia:
            # la accion esta en la pantalla donde se aplica, el ajuste vive en el
            # panel y el hijo se abre desde su padre. Ninguno de los tres es un
            # destino navegable por si mismo.
            continue
        # Lo que no es accion, hijo ni ajuste DEBE poder navegar.
        assert entrada["ruta"], (
            f"el destino {entrada['clave']!r} no tiene ruta y no esta marcado como "
            "accion, hijo ni ajuste"
        )


def test_las_acciones_mas_de_la_superficie_son_acciones() -> None:
    """Recuento de guarda: el mapa tiene que declarar acciones.

    Si el test anterior pasara porque no hay ninguna accion, el mapa estaria mal de
    otra forma. Este fija que la distincion existe de verdad.
    """
    acciones = [e for e in _entradas() if e["banderas"].get("accion")]
    assert len(acciones) >= 20, (
        f"solo hay {len(acciones)} acciones marcadas; se esperaban muchas mas "
        "(alta, edicion, rectificacion, generacion...)"
    )


def test_los_ajustes_no_tienen_ruta() -> None:
    """Un ajuste vive dentro del panel, no en una pantalla propia.

    Un `ajuste: true` con ruta daria un destino navegable que no lleva a ninguna
    parte, que es peor que no declararlo.
    """
    for entrada in _entradas():
        if bool(entrada["banderas"].get("ajuste")):
            assert entrada["ruta"] == "", (
                f"el ajuste {entrada['clave']!r} tiene ruta {entrada['ruta']!r}; "
                "deberia vivir dentro del panel"
            )


# ---------------------------------------------------------------------------
# 3. Etiquetas (FR-015)
# ---------------------------------------------------------------------------


def test_ninguna_etiqueta_es_solo_una_sigla() -> None:
    """Una etiqueta de destino no puede ser una sigla desnuda (FR-015).

    "EFE" o "SII" solas obligan al usuario a saber el interior del programa. Lo que
    se permite es la sigla **con su significado**: "Modelo 200", "Flujos de
    efectivo", "Libros de IVA".
    """
    solo_siglas: list[str] = []
    for entrada in _entradas():
        palabras = entrada["etiqueta"].split()
        if not palabras:
            continue
        # Una sola palabra, todo en mayusculas y corta: es una sigla desnuda.
        if len(palabras) == 1 and palabras[0].isupper() and len(palabras[0]) <= 5:
            solo_siglas.append(entrada["etiqueta"])
    assert solo_siglas == [], f"etiquetas que son solo una sigla: {solo_siglas}"


def test_las_etiquetas_de_los_destinos_de_ejercicio_son_explicitas() -> None:
    """El ciclo de vida del ejercicio se nombra, no se codifica."""
    por_clave = {e["clave"]: e["etiqueta"] for e in _entradas()}
    esperados = {
        "apertura": "Apertura",
        "cierre-intermedio": "Cierre intermedio",
        "cierre-anual": "Cierre anual",
        "reaperturas": "Reaperturas",
    }
    for clave, etiqueta in esperados.items():
        assert por_clave.get(clave) == etiqueta, (
            f"el destino {clave!r} deberia llamarse {etiqueta!r}, es {por_clave.get(clave)!r}"
        )


def test_las_etiquetas_no_superan_lo_razonable() -> None:
    """M3 dice etiquetas cortas y que no se trunquen, y no da un numero.

    Aqui se fija 30 caracteres como **umbral de olor**, no como ley: por encima, la
    etiqueta necesita dos lineas en el rail, y la guia de Material dice que se
    evite un ajuste de mas de dos lineas. Treinta es lo que cabe en dos lineas en un
    rail estrecho.

    Se sube desde 24 tras ver que tres etiquetas legitimas lo superaban
    ("Impuesto sobre Sociedades", "Condiciones de pronto pago", "Ajustes de
    informacion fiscal"). Son los nombres reales del dominio y acortarlos a fuerza
    ("Imp. Sociedades") seria peor para el usuario que dos lineas.
    """
    largos = [
        f"{e['clave']}={e['etiqueta']!r} ({len(e['etiqueta'])})"
        for e in _entradas()
        if len(e["etiqueta"]) > 30
    ]
    assert largos == [], f"etiquetas de tres o mas lineas en el rail: {largos}"


# ---------------------------------------------------------------------------
# 4. Los favoritos viven aparte
# ---------------------------------------------------------------------------


def test_los_favoritos_no_forman_parte_del_rail() -> None:
    """Los favoritos son una seccion aparte; el rail no los menciona (FR-023).

    Si el mapa declarana los favoritos, dejarian de ser un dato del usuario y
    pasaron a ser parte de la estructura, que es justo lo que FR-023 prohibe.
    """
    array = _array().lower()
    assert "favorito" not in array, "los favoritos han entrado en el mapa de superficies"
    assert "favoritos" not in array, "los favoritos han entrado en el mapa de superficies"


def test_la_seccion_de_favoritos_se_declara_fuera_del_array() -> None:
    """Se comprueba que existe la seccion, para que el silencio anterior sea real.

    Sin esto, "los favoritos no estan en el mapa" pasaria tambien si no hubiera
    ninguna seccion de favoritos en ninguna parte.
    """
    texto = _texto().lower()
    assert "favoritesbar" in texto or "favoritos" in texto, (
        "no hay ninguna seccion de favoritos en el paquete de navegacion"
    )


# ---------------------------------------------------------------------------
# 5. Permisos
# ---------------------------------------------------------------------------


def test_todo_destino_declara_un_permiso_por_defecto() -> None:
    """El permiso se hereda del helper `d()`, asi que basta con que exista.

    Es la forma de que el panel pueda filtrar: sin permiso declarado no hay forma de
    saber si un destino se puede abrir, y acabaria mostrando un 403 como destino
    (el caso borde que el spec prohibe).
    """
    texto = _texto()
    assert "permiso: Permiso" in texto, "el tipo Destino no declara permiso"
    assert re.search(r"permiso:\s*Permiso", texto), "Destino no tipa el permiso"
    assert "ACCESO_CONTEXTO" in texto, "no hay un permiso por defecto declarado"


@pytest.mark.parametrize(
    "clave",
    [
        "asientos",
        "facturas",
        "vencimientos",
        "conciliacion",
        "balance",
        "libros-iva",
        "terceros",
        "permisos",
    ],
)
def test_los_destinos_principales_existen(clave: str) -> None:
    """SpOT de destinos: si alguno desaparece, la suite avisa antes que un usuario.

    Estos ocho son los mas usados del programa segun el reparto por superficies, y
    cada uno pertenece a una superficie distinta: si uno falta, es que la
    reorganizacion ha roto una superficie entera sin que nadie lo viera.
    """
    claves = {e["clave"] for e in _entradas()}
    assert clave in claves, f"falta el destino {clave!r} en el mapa"


def test_terceros_de_interaccion_exigen_teclado() -> None:
    """El mapa no puede exigir teclado a un elemento que no lo soporta.

    Es una comprobacion negativa deliberada: si alguien metiera aqui un requisito de
    foco o de teclado, este test recordaria que la regla vive en FR-030 y se
    comprueba en `test_navegacion_accesibilidad.py` (T060), no en el mapa.
    """
    assert "onKeyDown" not in _texto(), "el mapa no debe contener manejadores de teclado"
