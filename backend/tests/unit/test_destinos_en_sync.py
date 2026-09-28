"""`surfaces.ts` y `destinos.py` no pueden separarse (SPEC-031, US4).

Este test es la unica red entre las dos copias del mapa de destinos. La fuente de verdad
es `surfaces.ts` (frontend); `services/navigation/destinos.py` es la copia que necesita
el backend para validar `PUT /favoritos/{destino}` y para marcar `accesible`/`desconocido`
en la lectura.

SIN ESTE TEST, EL FALLO ES SILENCIOSO Y TARDIO

Si se anade un destino en el panel y no en el backend, nada revienta al desplegar: el
panel lo muestra, el boton de favorito devuelve **404** y el usuario ve un destino que no
se puede marcar. Esa es la forma exacta de la que el catalogo backend existe para
evitar. El fallo aparece en produccion, en la accion del usuario, y no en la suite.

El caso inverso es mas insidioso: una clave en el backend que ya no esta en el panel pasa
desapercibida durante meses, porque solo la nota el usuario que pulso favorito en una
version anterior y lo ve desaparecer sin explicacion.
"""

from __future__ import annotations

import re
from pathlib import Path

from services.navigation.destinos import DESTINOS, es_conocido

RAIZ = Path(__file__).resolve().parents[3]
SURFACES = RAIZ / "frontend" / "src" / "components" / "navigation" / "surfaces.ts"

# Los destinos se declaran con la llamada auxiliar `d("clave", ...)`. Se busca esa forma y
# no cualquier cadena del fichero, para no recoger etiquetas, rutas ni nombres de icono.
# El patron es el MISMO que usa el generador: si uno cambia y el otro no, este test
# detecta tambien esa discrepancia, porque la cuenta no cuadra.
PATRON = re.compile(r'd\(\s*"([a-z0-9_-]+)"')

#: Entradas `{ ajuste: true }`: ajustes del panel **sin ruta propia**. No son destinos y
#: no se pueden marcar como favorito, porque un favorito sin ruta es un enlace a la nada.
#: La lista se comprueba contra el mapa, no se supone: si aparece otra, hay que decidir si
#: es un ajuste o un destino, y decidirlo a ciegas en el generador sería peor.
AJUSTES = {"ajustes-sii"}


def _es_ajuste(clave: str, texto: str) -> bool:
    """Si la llamada `d(...)` de esa clave lleva `{ ajuste: true }`."""
    patron = re.compile(
        r'd\(\s*"' + re.escape(clave) + r'".*?\),\n', re.DOTALL
    )
    m = patron.search(texto)
    return bool(m and re.search(r"ajuste:\s*true", m.group(0)))


def claves_del_panel() -> set[str]:
    texto = SURFACES.read_text(encoding="utf-8")
    return {
        clave
        for clave in PATRON.findall(texto)
        if not _es_ajuste(clave, texto)
    }


def test_los_ajustes_sin_ruta_estan_declarados_como_tales() -> None:
    """Que `AJUSTES` y el mapa digan lo mismo.

    Si `ajustes-sii` dejara de llevar `{ ajuste: true }` y `AJUSTES` no se actualizara, el
    generador volvería a meterla en `DESTINOS` y el backend aceptaría un favorito sin
    ruta. Las dos listas tienen que moverse juntas.
    """
    texto = SURFACES.read_text(encoding="utf-8")
    en_mapa = {c for c in PATRON.findall(texto) if _es_ajuste(c, texto)}
    assert en_mapa == AJUSTES, (
        f"el mapa declara {en_mapa} como ajustes y el test espera {AJUSTES}"
    )


def test_el_panel_declara_destinos() -> None:
    """Guardia previa: si el panel no declarara ninguno, el resto no significaria nada.

    Un cambio de sintaxis en `surfaces.ts` (por ejemplo pasar de `d("x", ...)` a un
    objeto literal) haria que este extractor devolviera el conjunto vacio. Sin esta
    comprobacion, la comparacion de abajo pasaria con las dos listas vacias y el test
    daria verde sin comprobar nada.
    """
    assert len(claves_del_panel()) > 50, "el extractor dejo de encontrar destinos"


def test_las_claves_del_backend_coinciden_con_el_panel() -> None:
    assert claves_del_panel() == DESTINOS, (
        "el mapa de destinos se ha separado:\n"
        f"  solo en surfaces.ts: {sorted(claves_del_panel() - DESTINOS)}\n"
        f"  solo en destinos.py:  {sorted(DESTINOS - claves_del_panel())}\n"
        "  anade la clave en los dos sitios, o regenera destinos.py"
    )


def test_ninguna_clave_esta_vacia_ni_tiene_espacios() -> None:
    """Una clave con espacios romperia la URL del favorito y la comparacion del mapa."""
    for clave in DESTINOS:
        assert clave, "hay una clave vacia en el catalogo"
        assert clave == clave.strip(), f"la clave {clave!r} tiene espacios"
        assert re.fullmatch(r"[a-z0-9_-]+", clave), f"la clave {clave!r} no es una slug"


def test_es_conocido_acepta_lo_declarado_y_rechaza_lo_ajeno() -> None:
    assert es_conocido("vencimientos")
    assert not es_conocido("ruta-que-nunca-existio")
    assert not es_conocido("")
    assert not es_conocido("Vencimientos"), "la clave es minuscula y no se normaliza"


def test_ningun_destino_sobrescribe_el_permiso_por_defecto() -> None:
    """`PERMISO_POR_DEFECTO` tiene que seguir siendo cierto para todos los destinos.

    El backend calcula `accesible` con un unico permiso (`acct:ver`) porque hoy ningun
    destino del mapa declara otro. Ese "hoy" es la parte peligrosa: si alguien anade
    `permiso: ["fiscal", "ver"]` a un destino del panel, el backend seguiria
    concediendolo con `acct:ver` y marcaria accesible lo que no lo es. Este test
    convierte ese descuido en un fallo de suite, que es justo cuando conviene.
    """
    texto = SURFACES.read_text(encoding="utf-8")
    sobrescritos = [
        m.group(1)
        for m in re.finditer(r'd\(\s*"([a-z0-9_-]+)"[^)]*permiso:', texto, re.DOTALL)
    ]
    assert not sobrescritos, (
        "estos destinos declaran permiso propio y el backend lo ignora: "
        f"{sobrescritos}. Modela el permiso en servicios/navigation/destinos.py"
    )


def test_es_accesible_distingue_permiso_de_destino_inexistente() -> None:
    """Con todos los permisos concedidos, un destino fuera del mapa sigue inaccesible.

    Es la parte de FR-024 que no depende de RBAC: "conservar pero no mostrar" porque la
    ruta se movio, no porque al usuario le falte un permiso.
    """
    from services.navigation.destinos import PERMISO_POR_DEFECTO, es_accesible

    todos = {PERMISO_POR_DEFECTO}
    assert es_accesible("vencimientos", todos)
    assert not es_accesible("ruta-que-nunca-existio", todos)
    # Sin permiso para el de por defecto, tampoco.
    assert not es_accesible("vencimientos", {("fiscal", "ver")})
    # `None` significa "sin datos de permisos" y concede, para no volver invisible el
    # favorito de nadie por un descuido del llamante.
    assert es_accesible("vencimientos", None)


def test_el_maximo_de_visibles_cinco_no_se_puede_subir_sin_actualizar_el_test() -> None:
    """El 5 de FR-025 esta en dos sitios: aqui y en el servicio.

    Si alguien sube `MAXIMO_VISIBLES` a 6 creyendo que es gratis, este test lo dice. El
    limite no es un detalle de implementacion: es lo que obliga a la interfaz a tener un
    "ver mas" en lugar de una barra que crece sin control.
    """
    from services.navigation.favoritos import MAXIMO_VISIBLES as EN_SERVICIO

    assert EN_SERVICIO == 5, "cambia el contrato de FR-025 y el panel con el"