"""Contexto de sesion: estado de ejercicio y recuento de asientos (SPEC-031, US1).

Cubre dos cosas y las dos tienen trampa.

**El estado derivado (research D4).** Hay DOS fuentes de estado de ejercicio que
pueden discrepar: `EjercicioContable` (SPEC-009, tres estados) y `FiscalYear`
(SPEC-004, un booleano). El caso real es que discrepen, porque el cierre de
informes escribe en una y la apertura escribe en la otra. La regla es que
prevalece la mas restrictiva, porque mostrar `abierto` cuando la escritura se va a
rechazar es la peor combinacion posible en un control de entrada.

**El recuento.** Se cuenta por la columna `ejercicio` del propio asiento, y no por
un rango de fechas derivado. `journal_entry.ejercicio` es NOT NULL, la rellena el
motor de SPEC-002 con `fecha.year`, y participa en la restriccion
`uq_journal_entry_tenant_numero (empresa_id, ejercicio, numero_asiento)`.

Eso corrige el diseno del plan en dos puntos:

1. El valor autoritativo es el que esta guardado, no el que se deduce de la fecha.
2. **No hace falta la migracion `023_indice_contexto.sql`.** El indice unico ya
   tiene `(empresa_id, ejercicio)` como prefijo y un `COUNT` con igualdad en esas
   dos columnas lo recorre. T074 queda cancelada por esto, no por otra razon.

El filtro `empresa_id` va primero y SIEMPRE (constitution III y V(b)), y el estado
es `POSTED` porque un borrador o un cancelado no son apuntes del libro.

Estos tests se escribieron ANTES que existiera `services/navigation/contexto.py`, y
por eso empezaron fallando con `ModuleNotFoundError`. Ese es el orden que exige la
constitution V.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.fiscal_year import FiscalYear
from models.acct.journal import JournalEntry, JournalEntryTipo
from models.fiscal.ejercicio import EjercicioContable, EjercicioEstado
from services.navigation.contexto import (
    ABIERTO,
    CERRADO,
    CON_APERTURA,
    contar_asientos,
    derivar_estado,
    es_actual,
    listar_ejercicios,
)
from tests.conftest import crear_empresas, sembrar_empresas_pgc

EMPRESA = 10
OTRA_EMPRESA = 20


def _asiento(
    empresa_id: int,
    ejercicio: int,
    fecha: dt.date,
    numero: int,
    estado: str = "POSTED",
) -> JournalEntry:
    return JournalEntry(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        numero_asiento=numero,
        fecha=fecha,
        concepto="Apunte de prueba",
        estado=estado,
        tipo=JournalEntryTipo.GENERAL,
    )


async def _sembrar(db_session: AsyncSession, filas: list[JournalEntry]) -> None:
    db_session.add_all(filas)
    await db_session.flush()


# ---------------------------------------------------------------------------
# Derivacion del estado
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("estado_contable", "is_closed", "esperado"),
    [
        # La mas restrictiva gana: cualquiera de las dos fuentes cerrada -> cerrado.
        (EjercicioEstado.cerrado, False, CERRADO),
        (EjercicioEstado.abierto, True, CERRADO),
        (EjercicioEstado.cerrado, True, CERRADO),
        # Sin cierre en ninguna de las dos fuentes.
        (EjercicioEstado.abierto, False, ABIERTO),
        (EjercicioEstado.con_apertura, False, CON_APERTURA),
        # `con_apertura` con FiscalYear cerrada sigue siendo cerrado: a un
        # ejercicio con apertura al que le cerraron el ano deja de admitir asientos.
        (EjercicioEstado.con_apertura, True, CERRADO),
    ],
)
def test_derivar_estado_prevalece_el_mas_restrictivo(
    estado_contable: EjercicioEstado, is_closed: bool, esperado: str
) -> None:
    assert derivar_estado(estado_contable, is_closed) == esperado


@pytest.mark.parametrize("is_closed", [False, True])
def test_derivar_estado_sin_ejercicio_contable(is_closed: bool) -> None:
    """Solo existe `FiscalYear`: manda `is_closed`.

    Es el caso de una empresa con anos de informes a la que nunca se le abrio un
    ejercicio contable. No es un error: se resuelve.
    """
    assert derivar_estado(None, is_closed) == (CERRADO if is_closed else ABIERTO)


def test_derivar_estado_sin_ninguna_fuente() -> None:
    """Sin filas en ninguna de las dos tablas, el ano no existe.

    Se devuelve `abierto` por la convencion de SPEC-004, pero la capa de contexto
    marca ese caso como `es_seleccionable: false`, que es lo que impide elegirlo.
    """
    assert derivar_estado(None, None) == ABIERTO


def test_es_actual_es_el_ano_en_curso() -> None:
    """Regla explicita de "ejercicio actual" (CHK007).

    Por comparacion con el ano en curso, y no por "el mas reciente que exista": el
    caso que motiva la feature es contabilizar en dos ejercicios a la vez, y si el
    anterior fuese siempre el activo, el 31 de diciembre se estaria en el
    equivocado.
    """
    hoy = dt.date(2026, 7, 15)
    assert es_actual(2026, hoy) is True
    assert es_actual(2025, hoy) is False
    assert es_actual(2027, hoy) is False


# ---------------------------------------------------------------------------
# Recuento de asientos
# ---------------------------------------------------------------------------


async def test_contar_asientos_por_ejercicio(db_session: AsyncSession) -> None:
    await crear_empresas(db_session, EMPRESA, OTRA_EMPRESA)
    await _sembrar(
        db_session,
        [
            _asiento(EMPRESA, 2025, dt.date(2025, 3, 15), 1),
            _asiento(EMPRESA, 2025, dt.date(2025, 12, 31), 2),
            _asiento(EMPRESA, 2026, dt.date(2026, 1, 1), 3),
            # Otra empresa, mismos ejercicios: no suma en los totales de la primera.
            _asiento(OTRA_EMPRESA, 2025, dt.date(2025, 3, 15), 1),
            _asiento(OTRA_EMPRESA, 2026, dt.date(2026, 1, 1), 2),
        ],
    )

    assert await contar_asientos(db_session, empresa_id=EMPRESA, ejercicio=2025) == 2
    assert await contar_asientos(db_session, empresa_id=EMPRESA, ejercicio=2026) == 1
    assert await contar_asientos(db_session, empresa_id=OTRA_EMPRESA, ejercicio=2025) == 1
    assert await contar_asientos(db_session, empresa_id=OTRA_EMPRESA, ejercicio=2026) == 1


async def test_contar_asientos_aisla_empresas(db_session: AsyncSession) -> None:
    """Principio V(b): el total de una empresa no incluye asientos de otra.

    Se comprueba con el mismo ejercicio y la misma fecha en las dos empresas, que
    es justo el caso que un filtro por fecha sin `empresa_id` dejaria pasar.
    """
    await crear_empresas(db_session, EMPRESA, OTRA_EMPRESA)
    await _sembrar(
        db_session,
        [
            _asiento(EMPRESA, 2025, dt.date(2025, 6, 1), 1),
            _asiento(OTRA_EMPRESA, 2025, dt.date(2025, 6, 1), 1),
            _asiento(OTRA_EMPRESA, 2025, dt.date(2025, 7, 1), 2),
        ],
    )
    assert await contar_asientos(db_session, empresa_id=EMPRESA, ejercicio=2025) == 1
    assert await contar_asientos(db_session, empresa_id=OTRA_EMPRESA, ejercicio=2025) == 2


async def test_contar_asientos_excluye_borradores_y_cancelados(
    db_session: AsyncSession,
) -> None:
    """Solo POSTED cuenta. Un borrador no es un apunte del libro."""
    await crear_empresas(db_session, EMPRESA)
    await _sembrar(
        db_session,
        [
            _asiento(EMPRESA, 2026, dt.date(2026, 2, 1), 1),
            _asiento(EMPRESA, 2026, dt.date(2026, 2, 2), 2, estado="DRAFT"),
            _asiento(EMPRESA, 2026, dt.date(2026, 2, 3), 3, estado="CANCELLED"),
        ],
    )
    assert await contar_asientos(db_session, empresa_id=EMPRESA, ejercicio=2026) == 1


async def test_contar_asientos_ejercicio_sin_asientos(db_session: AsyncSession) -> None:
    await crear_empresas(db_session, EMPRESA)
    assert await contar_asientos(db_session, empresa_id=EMPRESA, ejercicio=2026) == 0


async def test_contar_asientos_ejercicio_inexistente(db_session: AsyncSession) -> None:
    """Un ejercicio que la empresa nunca uso devuelve 0, no error."""
    await crear_empresas(db_session, EMPRESA)
    await _sembrar(db_session, [_asiento(EMPRESA, 2025, dt.date(2025, 1, 1), 1)])
    assert await contar_asientos(db_session, empresa_id=EMPRESA, ejercicio=1999) == 0


async def test_contar_asientos_sin_doble_conteo_en_el_cambio_de_ano(
    db_session: AsyncSession,
) -> None:
    """El 31 de diciembre y el 1 de enero son ejercicios distintos, sin solape.

    Con un filtro por rango de fechas mal hecho, el dia de cambio se contaria en
    los dos. Como el ejercicio va guardado en el asiento, no hay forma de que pase.
    """
    await crear_empresas(db_session, EMPRESA)
    await _sembrar(
        db_session,
        [
            _asiento(EMPRESA, 2025, dt.date(2025, 12, 31), 1),
            _asiento(EMPRESA, 2026, dt.date(2026, 1, 1), 1),
        ],
    )
    en_2025 = await contar_asientos(db_session, empresa_id=EMPRESA, ejercicio=2025)
    en_2026 = await contar_asientos(db_session, empresa_id=EMPRESA, ejercicio=2026)
    assert (en_2025, en_2026) == (1, 1)
    assert en_2025 + en_2026 == 2


# ---------------------------------------------------------------------------
# Las dos fuentes de estado conviven
# ---------------------------------------------------------------------------


async def test_las_dos_fuentes_conviven_para_la_misma_empresa(
    db_session: AsyncSession,
) -> None:
    """Un ano puede existir en `FiscalYear`, en `EjercicioContable` o en ambos.

    La feature NO unifica las tablas: eso tocaria 15 specs. Lo que hace es leer las
    dos y derivar un estado unico, que es lo que se muestra y lo que gobierna la
    escritura.
    """
    await sembrar_empresas_pgc(db_session, EMPRESA)
    db_session.add_all(
        [
            # 2025: cerrado en FiscalYear, abierto en EjercicioContable. Discrepan.
            FiscalYear(
                empresa_id=EMPRESA,
                year=2025,
                date_start=dt.date(2025, 1, 1),
                date_end=dt.date(2025, 12, 31),
                is_closed=True,
            ),
            EjercicioContable(
                empresa_id=EMPRESA,
                ejercicio=2025,
                fecha_inicio=dt.date(2025, 1, 1),
                fecha_fin=dt.date(2025, 12, 31),
                estado=EjercicioEstado.abierto,
            ),
            # 2026: solo en EjercicioContable.
            EjercicioContable(
                empresa_id=EMPRESA,
                ejercicio=2026,
                fecha_inicio=dt.date(2026, 1, 1),
                fecha_fin=dt.date(2026, 12, 31),
                estado=EjercicioEstado.abierto,
            ),
        ]
    )
    await db_session.flush()

    filas = await listar_ejercicios(db_session, empresa_id=EMPRESA, hoy=dt.date(2026, 7, 1))
    por_anio = {f["ejercicio"]: f for f in filas}

    assert set(por_anio) == {2025, 2026}
    assert por_anio[2025]["estado"] == CERRADO
    assert por_anio[2026]["estado"] == ABIERTO
    assert por_anio[2025]["es_seleccionable"] is False
    assert por_anio[2026]["es_seleccionable"] is True
    assert por_anio[2026]["es_actual"] is True
    assert por_anio[2025]["es_actual"] is False


async def test_listar_ejercicios_aisla_empresas(db_session: AsyncSession) -> None:
    """El listado de contexto solo devuelve ejercicios de la empresa pedida."""
    await crear_empresas(db_session, EMPRESA, OTRA_EMPRESA)
    db_session.add_all(
        [
            EjercicioContable(
                empresa_id=EMPRESA,
                ejercicio=2026,
                fecha_inicio=dt.date(2026, 1, 1),
                fecha_fin=dt.date(2026, 12, 31),
                estado=EjercicioEstado.abierto,
            ),
            EjercicioContable(
                empresa_id=OTRA_EMPRESA,
                ejercicio=2024,
                fecha_inicio=dt.date(2024, 1, 1),
                fecha_fin=dt.date(2024, 12, 31),
                estado=EjercicioEstado.cerrado,
            ),
        ]
    )
    await db_session.flush()

    filas = await listar_ejercicios(db_session, empresa_id=EMPRESA, hoy=dt.date(2026, 7, 1))
    assert {f["ejercicio"] for f in filas} == {2026}


async def test_listar_ejercicios_de_una_empresa_sin_ejercicios(
    db_session: AsyncSession,
) -> None:
    """Una empresa recien creada no tiene ejercicios: la lista va vacia, no falla."""
    await crear_empresas(db_session, EMPRESA)
    filas = await listar_ejercicios(db_session, empresa_id=EMPRESA, hoy=dt.date(2026, 7, 1))
    assert filas == []
