"""Validacion de `X-Ejercicio-Activa` (SPEC-031, US3, tarea T030).

Cubre las tres decisiones de research D3:

1. **La cabecera es no confiable.** Llega del cliente, asi que se valida contra los
   ejercicios de la empresa antes de usarse. Un valor mal formado y un valor ajeno
   son el mismo error a proposito: distinguirlos confirmaria que ese ejercicio existe
   en otro tenant (constitution III).
2. **El valor por defecto.** Sin cabecera, manda el ano en curso.
3. **La precedencia (FR-007).** Un `?ejercicio=` explicito en la URL **gana** a la
   cabecera. La cabecera es un default, nunca una imposicion: si No, abrir
   `/libros-iva?ejercicio=2025` escribiria en 2026.

Y un caso que se parece a un error y no lo es: **un ejercicio cerrado se rechaza
como "no pertenece"**, no con un codigo de cerrado. Es el mismo codigo a proposito,
porque quien pregunta no puede distinguir "no existe" de "es de otra empresa", y
porque la respuesta no debe revelar en que empresas hay ejercicios.
"""

from __future__ import annotations

import pytest

from services.navigation.contexto import (
    ABIERTO,
    CERRADO,
    CON_APERTURA,
    EjercicioResuelto,
)
from services.navigation.ejercicio_activo import (
    elegir_del_contexto,
    es_utilizable,
    parsear,
    validar_solicitado,
)


def _fila(
    ejercicio: int,
    estado: str = ABIERTO,
    seleccionable: bool = True,
    es_actual: bool = False,
) -> EjercicioResuelto:
    return {
        "ejercicio": ejercicio,
        "estado": estado,
        "es_actual": es_actual,
        "n_asientos": 0,
        "es_seleccionable": seleccionable,
    }


# ---------------------------------------------------------------------------
# Interpretar la cabecera
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("crudo", "esperado"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("2026", 2026),
        (" 2026 ", 2026),
        ("1999", 1999),
    ],
)
def test_parsear_cabecera_valida(crudo: str | None, esperado: int | None) -> None:
    """Los espacios no son un error: los proxies HTTP los anaden."""
    assert parsear(crudo) == esperado


@pytest.mark.parametrize(
    "crudo",
    ["abc", "2026a", "25", "-2026", "2.026", "2026; DROP TABLE", "١٢٣"],
)
def test_parsear_cabecera_mal_formada(crudo: str) -> None:
    """Un valor presente pero basura es un error del cliente, no un ausente.

    Se distingue a proposito: "no has enviado nada" es legitimo y el servidor
    resuelve; "has enviado basura" es un fallo que el usuario debe ver.
    """
    with pytest.raises(Exception) as exc:
        parsear(crudo)
    assert exc.value.code == "ejercicio_invalido"


@pytest.mark.parametrize("crudo", ["1899", "3000", "0000", "99999"])
def test_parsear_cabecera_fuera_de_rango(crudo: str) -> None:
    """Cuatro digitas y en un rango que no se va a agotar.

    Un ano de tres digitas casi siempre es un error de tecleo, y tratarlo como
    1926 daria un resultado plausible y equivocado.
    """
    with pytest.raises(Exception) as exc:
        parsear(crudo)
    assert exc.value.code == "ejercicio_invalido"


# ---------------------------------------------------------------------------
# Validar contra la empresa
# ---------------------------------------------------------------------------


def test_sin_cabecera_no_se_valida_nada() -> None:
    """`None` es un valor legitimo: el servidor decide."""
    assert validar_solicitado([_fila(2026)], None) is None


def test_un_ejercicio_de_la_empresa_se_acepta() -> None:
    filas = [_fila(2025), _fila(2026)]
    assert validar_solicitado(filas, 2025) == 2025


def test_un_ejercicio_inexistente_se_rechaza() -> None:
    with pytest.raises(Exception) as exc:
        validar_solicitado([_fila(2026)], 2020)
    assert exc.value.code == "ejercicio_no_pertenece_a_empresa"


def test_un_ejercicio_cerrado_se_rechaza() -> None:
    """Un cerrado no es utilizable para escribir, y se rechaza con el codigo de ajeno.

    El codigo es el mismo a proposito: quien pregunta no puede distinguir "no
    existe" de "es de otra empresa", y la respuesta no debe revelar nada del otro
    tenant. Ademas, el selector **si** lo muestra en la lista (para que el usuario
    vea que existe y por que no puede escribir), pero no lo deja activo.
    """
    filas = [_fila(2025, CERRADO, seleccionable=False), _fila(2026)]
    with pytest.raises(Exception) as exc:
        validar_solicitado(filas, 2025)
    assert exc.value.code == "ejercicio_no_pertenece_a_empresa"


def test_un_ejercicio_solo_de_informes_no_se_acepta() -> None:
    """Un ano que existe en `FiscalYear` pero no como ejercicio contable no admite
    asientos, asi que tampoco es utilizable.

    Es el caso de una empresa con informes de 2024 a la que nunca se le abrio un
    ejercicio: el ano aparece en la lista, visible, pero no se puede escribir en el.
    """
    filas = [_fila(2024, ABIERTO, seleccionable=False), _fila(2026)]
    with pytest.raises(Exception) as exc:
        validar_solicitado(filas, 2024)
    assert exc.value.code == "ejercicio_no_pertenece_a_empresa"


def test_los_cuatro_estados_se_tratan_segun_corresponde() -> None:
    """Tabla completa, para que un estado nuevo no pase por inadvertido."""
    filas = [
        _fila(2024, ABIERTO, seleccionable=True),
        _fila(2025, CON_APERTURA, seleccionable=True),
        _fila(2023, CERRADO, seleccionable=False),
    ]
    assert es_utilizable(2024, filas) is True
    assert es_utilizable(2025, filas) is True
    assert es_utilizable(2023, filas) is False
    assert es_utilizable(1999, filas) is False


# ---------------------------------------------------------------------------
# Precedencia: la URL gana a la cabecera (FR-007)
# ---------------------------------------------------------------------------


def test_la_url_gana_a_la_cabecera() -> None:
    """Es la regla que impide que abrir una URL con `?ejercicio=` escriba en otro.

    Sin esta precedencia, `/libros-iva?ejercicio=2025` generaria un apunte en 2026
    porque la cabecera digiera 2026. Seria el peor fallo posible de la feature.
    """
    filas = [_fila(2025), _fila(2026)]
    assert elegir_del_contexto(filas, cabecera=2026, query=2025) == 2025
    assert elegir_del_contexto(filas, cabecera=2025, query=2026) == 2026


def test_sin_query_manda_la_cabecera() -> None:
    filas = [_fila(2025), _fila(2026)]
    assert elegir_del_contexto(filas, cabecera=2025, query=None) == 2025


def test_solo_cabecera_usa_el_ano_en_curso() -> None:
    """Sin nada, el ano en curso, que es la definicion de `es_actual` (CHK007)."""
    filas = [_fila(2025), _fila(2026, es_actual=True)]
    assert elegir_del_contexto(filas, cabecera=None, query=None) == 2026


def test_una_url_invalida_no_cae_a_la_cabecera() -> None:
    """Un `?ejercicio=1999` MUST fallar, no resolverse al año de la cabecera.

    Caer a la cabecera seria peor que el fallo: el usuario cree que esta en 1999 y
    en realidad esta en otro, y el apunte entra en el ejercicio equivocado sin
    que nada lo diga.
    """
    filas = [_fila(2026)]
    with pytest.raises(Exception) as exc:
        elegir_del_contexto(filas, cabecera=2026, query=1999)
    assert exc.value.code == "ejercicio_no_pertenece_a_empresa"


def test_una_cabecera_invalida_se_ignora_si_hay_una_query_valida() -> None:
    """Con query valida, la cabecera no se mira. Es lo que dice FR-007.

    Escribi este test al principio exigiendo lo contrario, y era incorrecto: si una
    cabecera invalida bloquease una eleccion explicita y valida, FR-007 ("la eleccion
    explicita prevalece sobre el ejercicio activo") se cumpliria solo a medias. Y
    ademas la cabecera viaja en **todas** las peticiones, asi que bloquear por ella
    convertiria un defecto de cliente en un bloqueo global del programa.

    Por eso se fija aqui el comportamiento correcto, y no la excepcion.
    """
    filas = [_fila(2025), _fila(2026)]
    assert elegir_del_contexto(filas, cabecera=1999, query=2026) == 2026
    assert elegir_del_contexto(filas, cabecera=3000, query=2025) == 2025


def test_sin_query_una_cabecera_invalida_falla() -> None:
    """Sin query, la cabecera es la unica fuente y si es invalida, se rechaza."""
    filas = [_fila(2025), _fila(2026)]
    with pytest.raises(Exception) as exc:
        elegir_del_contexto(filas, cabecera=1999, query=None)
    assert exc.value.code == "ejercicio_no_pertenece_a_empresa"


def test_una_query_abierta_es_usable_aunque_la_cabecera_no_lo_sea() -> None:
    """El orden es: primero se resuelve, despues se valida la eleccion.

    Si se validara la cabecera antes, un ejercicio cerrado en la cabecera impediria
    trabajar en uno abierto que la URL pide explicitamente.
    """
    filas = [_fila(2025, CERRADO, seleccionable=False), _fila(2026)]
    assert elegir_del_contexto(filas, cabecera=2025, query=2026) == 2026
