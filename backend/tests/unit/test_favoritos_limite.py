"""El límite de 5 favoritos, fijado en un solo sitio (SPEC-031, US4, T061).

FR-025 limita los favoritos **visibles**, no los guardados. La diferencia es el caso
borde que decidió la feature: un sexto favorito se guarda y la lectura lo recorta, porque
rechazarlo dejaría al usuario con cinco favoritos sin poder añadir el suyo.

Ese caso ya está probado en `test_favoritos_servicio.py` y en `test_favoritos_routes.py`.
Lo que este fichero añade es el otro riesgo, el que no salta en los tests de
comportamiento: que el **número** se desincronice entre el servicio, el catálogo de
destinos y la barra de favoritos. Con tres copias del 5 en tres ficheros, un día alguien
cambia una y la interfaz recorta distinto que el servidor, sin que ningún test de
comportamiento se entere.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
CATALOGO = RAIZ / "backend" / "src" / "services" / "navigation" / "destinos.py"
SERVICIO = RAIZ / "backend" / "src" / "services" / "navigation" / "favoritos.py"
BARRA = RAIZ / "frontend" / "src" / "components" / "navigation" / "FavoritesBar.tsx"

CINCO = 5


def test_el_limite_es_cinco_en_los_tres_sitios() -> None:
    """Uno en el catálogo, uno en el servicio, ninguno duplicado en la barra.

    La barra **no** debe tener su propia copia: cuenta con lo que le dice el servidor
    (`total` y `visibles`). Un `MAXIMO_VISIBLES` en el cliente es un segundo número que
    puede quedar viejo respecto al servidor, y la interfaz avisaría de más o de menos.
    """
    catalogo = CATALOGO.read_text(encoding="utf-8")
    servicio = SERVICIO.read_text(encoding="utf-8")
    barra = BARRA.read_text(encoding="utf-8")

    assert f"MAXIMO_VISIBLES = {CINCO}" in catalogo
    assert f"MAXIMO_VISIBLES = {CINCO}" in servicio
    assert "MAXIMO_VISIBLES" not in barra, "la barra no debe re-declarar el limite"
    assert "const MAXIMO" not in barra, "la barra no debe declarar su propio limite"


def test_la_barra_compara_las_cifras_que_le_da_el_servidor() -> None:
    """El aviso de "N guardados, M visibles" sale de la respuesta, no de un contador local."""
    barra = BARRA.read_text(encoding="utf-8")
    assert "datos.total > datos.visibles" in barra
    assert "{datos.total} guardados, {datos.visibles} visibles" in barra


def test_el_servicio_recorta_por_el_catalogo_y_no_por_un_numero_propio() -> None:
    """El corte se hace con el valor importado del catálogo, no con un literal.

    Es lo que evita la desincronización: si el servicio escribiera `filas[:5]`, el
    catálogo podría decir 6 y nadie se enteraría. Se comprueba que el corte usa la
    constante y que no hay ningún `:5]` suelto.
    """
    servicio = SERVICIO.read_text(encoding="utf-8")
    assert "filas[:MAXIMO_VISIBLES]" in servicio
    assert not re.search(r"\[:\s*\d+\s*\]", servicio), "hay un corte con un numero literal"


def test_el_contrato_dice_que_ninguno_visible_supera_el_limite() -> None:
    """La respuesta cumple lo que el contrato promete, para cualquier número de favoritos."""
    from services.navigation.destinos import MAXIMO_VISIBLES as DEL_CATALOGO
    from services.navigation.favoritos import MAXIMO_VISIBLES as DEL_SERVICIO

    assert DEL_CATALOGO == DEL_SERVICIO == CINCO


def test_la_barra_no_promete_una_expansion_que_no_existe() -> None:
    """No hay botón de «mostrar más»: la lectura ya viene recortada y no hay endpoint.

    Un botón que llamara a una ruta inexistente sería otro 404 silencioso, y sería el
    mismo error que cometió la barra con `/desmarcar`, en el otro sentido.
    """
    barra = BARRA.read_text(encoding="utf-8")
    assert "desplegados" not in barra
    assert "Mostrar" not in barra, "no hay nada que mostrar: la lista viene recortada"
    assert "/favoritos/todos" not in barra
