"""El catalogo de formatos de extracto esta escrito dos veces (SPEC-013).

Una en el backend (`services/reconciliation/layouts.py::LAYOUTS`), que es la que
valida la API, y otra en el desplegable del frontend
(`app/conciliacion/importar/page.tsx::LAYOUTS`). Son el mismo catalogo visto desde
dos lados, y dos listas se separan: anadir un parser sin anadir la opcion deja un
formato que el backend acepta y que el usuario no puede pedir, y quitar la opcion
deja una opcion que el usuario puede marcar y que el backend rechaza.

Estos tests no comprueban que el boton funcione. Comprueban que las dos listas digan
lo mismo y que la API no acepte un formato fuera del catalogo.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from api.reconciliation import _validar_layout
from services.reconciliation.layouts import LAYOUTS, LAYOUTS_XLSX

RAIZ = Path(__file__).resolve().parents[3]
PAGINA = RAIZ / "frontend" / "src" / "app" / "conciliacion" / "importar" / "page.tsx"


def _valores_del_desplegable() -> list[str]:
    texto = PAGINA.read_text(encoding="utf-8")
    bloque = texto[texto.index("const LAYOUTS") : texto.index("];", texto.index("const LAYOUTS"))]
    return re.findall(r'valor:\s*"([^"]+)"', bloque)


def test_el_desplegable_y_el_catalogo_dicen_lo_mismo() -> None:
    assert _valores_del_desplegable() == list(LAYOUTS)


def test_el_xlsx_esta_en_el_desplegable() -> None:
    """La correccion que motivo esto: el formato que da el banco no se podia elegir."""
    assert "xlsx_bancario" in _valores_del_desplegable()


def test_el_navegador_deja_elegir_un_xlsx() -> None:
    """`accept` sin `.xlsx` hace que el fichero no aparezca ni en el dialogo del
    sistema, y el usuario ve un error de 'fichero no valido' sin poder hacer nada."""
    texto = PAGINA.read_text(encoding="utf-8")
    accept = re.search(r'accept="([^"]+)"', texto)
    assert accept is not None, "el input de fichero no declara accept"
    extensiones = {a.strip().lstrip(".").lower() for a in accept.group(1).split(",")}
    assert {"txt", "csv", "xlsx"}.issubset(extensiones)


def test_los_formatos_de_hoja_estan_declarados_una_sola_vez() -> None:
    assert list(LAYOUTS_XLSX) == ["xlsx_bancario"]
    assert set(LAYOUTS_XLSX).issubset(LAYOUTS)


def test_la_api_acepta_los_formatos_del_catalogo() -> None:
    for nombre in LAYOUTS:
        assert _validar_layout(nombre) == nombre


@pytest.mark.parametrize("nombre", ["xlsx", "", "csv", "XLSX", "norma43", "txt"])
def test_la_api_rechaza_un_formato_fuera_del_catalogo(nombre: str) -> None:
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        _validar_layout(nombre)
    assert exc.value.status_code == 422
    assert exc.value.detail["error"] == "layout_desconocido"


def test_el_error_de_formato_dice_los_que_si_valen() -> None:
    """Un error que no dice como arreglarlo obliga a buscar la lista a mano."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        _validar_layout("xlsx")
    assert set(exc.value.detail["soportados"]) == set(LAYOUTS)
