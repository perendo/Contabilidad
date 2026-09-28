"""Resolucion del contexto de sesion (SPEC-031, US1).

Responde a la pregunta que el shell necesita en una sola llamada: quien eres, en que
empresa estas, en que ejercicio y cuantos asientos lleva cada uno.

LOS TRES FILTROS QUE NO SE PUEDEN OLVIDAR (constitution III y V(b))

1. `empresa_id` va SIEMPRE primero y SIEMPRE viene de la sesion. Nunca del
   cliente. Es la misma regla que `get_empresa_id` aplica en la capa de API: aqui
   el servicio la recibe como parametro y el endpoint se la entrega desde la
   sesion autenticada.
2. `X-Ejercicio-Activa` es un valor **no confiable** del cliente. Se valida
   contra la empresa antes de usarse (research D3), de modo que el ejercicio es un
   filtro interno del tenant y no una frontera de tenant.
3. El recuento filtra por empresa, por estado POSTED y por rango de fechas. El
   rango se compara con `>=` y `<` porque los limites de dos ejercicios
   consecutivos hacen touche: con `<=` el dia de cambio se contaria dos veces.
"""

from __future__ import annotations

import datetime as dt
from typing import TypedDict

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.fiscal_year import FiscalYear
from models.acct.journal import JournalEntry
from models.fiscal.ejercicio import EjercicioContable, EjercicioEstado

#: Estados que puede devolver la derivacion. Los mismos valores que el contrato
#: `api-contracts.md` y que el tipo `EstadoEjercicio` del cliente.
ABIERTO = "abierto"
CON_APERTURA = "con_apertura"
CERRADO = "cerrado"


class EjercicioResuelto(TypedDict):
    """Fila de un ejercicio en el contexto. Es el contrato de la API."""

    ejercicio: int
    estado: str
    es_actual: bool
    n_asientos: int
    es_seleccionable: bool


def hoy_utc() -> dt.date:
    """Hoy en UTC.

    El repositorio trabaja en UTC de punta a punta (constitution, Timestamps), y
    `date.today()` usa la zona horaria local del servidor: en un servidor en UTC+2
    las ultimas horas del 31 de diciembre darian 1 de enero, y `es_actual`
    seleccionaria el ejercicio equivocado. Es exactamente el caso que la feature
    trata de evitar.
    """
    return dt.datetime.now(dt.timezone.utc).date()


def derivar_estado(
    estado_contable: EjercicioEstado | str | None, is_closed: bool | None
) -> str:
    """Estado unico de un ejercicio a partir de las dos fuentes (research D4).

    `EjercicioContable` (SPEC-009) modela el ciclo de vida con tres estados y es la
    fuente de verdad. `FiscalYear` (SPEC-004) solo tiene un booleano `is_closed` y
    la usa el cierre de informes. Las dos pueden discrepar y el caso real es que
    lo hagan: un ano cerrado por `cerrar_ejercicio` puede seguir `abierto` en
    `EjercicioContable`.

    **Prevalece la mas restrictiva.** Mostrar `abierto` cuando la escritura se va
    a rechazar es la peor combinacion posible en un control de entrada, asi que el
    estado derivado gobierna a la vez lo que se ve y lo que se puede escribir, y
    por eso no pueden discrepar (FR-019).

    Sin ninguna de las dos filas se devuelve `abierto`, por la convencion de
    SPEC-004 de que un ano inexistente esta abierto. La capa de contexto marca ese
    caso como `es_seleccionable: false`, que es lo que impide elegirlo.
    """
    cerrado_por_contable = estado_contable == EjercicioEstado.cerrado
    if cerrado_por_contable or bool(is_closed):
        return CERRADO
    if estado_contable == EjercicioEstado.con_apertura:
        return CON_APERTURA
    return ABIERTO


async def contar_asientos(
    db: AsyncSession, *, empresa_id: int, ejercicio: int
) -> int:
    """Asientos POSTED de una empresa en un ejercicio.

    Filtra por la columna `ejercicio` del propio asiento, no por un rango de fechas
    derivado. La columna es NOT NULL, la rellena el motor de SPEC-002 con
    `fecha.year` y forma parte de `uq_journal_entry_tenant_numero
    (empresa_id, ejercicio, numero_asiento)`, asi que es el valor autoritativo y el
    filtro aprovecha el indice unico como prefijo. Un recuento por rango de fechas
    volveria a deducir lo que el asiento ya sabe, y con una empresa de ejercicio
    desplazado contaria mal.

    `empresa_id` va primero y siempre (constitution III). `POSTED` porque un
    borrador o un cancelado no son apuntes del libro.
    """
    total = await db.scalar(
        sa.select(sa.func.count())
        .select_from(JournalEntry)
        .where(
            JournalEntry.empresa_id == empresa_id,
            JournalEntry.ejercicio == ejercicio,
            JournalEntry.estado == "POSTED",
        )
    )
    return int(total or 0)


async def _filas_por_ejercicio(
    db: AsyncSession, empresa_id: int
) -> tuple[dict[int, EjercicioContable], dict[int, FiscalYear]]:
    """Las dos fuentes de estado de una empresa, indexadas por ejercicio."""
    contables = (
        await db.scalars(
            sa.select(EjercicioContable)
            .where(EjercicioContable.empresa_id == empresa_id)
            .order_by(EjercicioContable.ejercicio)
        )
    ).all()
    fiscales = (
        await db.scalars(
            sa.select(FiscalYear)
            .where(FiscalYear.empresa_id == empresa_id)
            .order_by(FiscalYear.year)
        )
    ).all()
    return (
        {c.ejercicio: c for c in contables},
        {f.year: f for f in fiscales},
    )


def es_actual(ejercicio: int, hoy: dt.date | None = None) -> bool:
    """Regla explicita de "ejercicio actual" (CHK007).

    Se define por comparacion con el ano en curso y no por "el mas reciente que
    exista", porque el caso motivador de la feature es contabilizar en dos
    ejercicios a la vez: si el anterior fuera siempre el activo, el 31 de
    diciembre se estaria en el equivocado.
    """
    referencia = hoy or hoy_utc()
    return ejercicio == referencia.year


async def listar_ejercicios(
    db: AsyncSession,
    *,
    empresa_id: int,
    hoy: dt.date | None = None,
) -> list[EjercicioResuelto]:
    """Todos los ejercicios de la empresa, con su estado derivado y su contador.

    Solo los de esa empresa: es el aislamiento de la constitution III aplicado al
    listado de contexto.
    """
    contables, fiscales = await _filas_por_ejercicio(db, empresa_id)

    # La union de las dos fuentes: un ano puede existir solo en `FiscalYear`.
    ejercicios = sorted(set(contables) | set(fiscales))
    filas: list[EjercicioResuelto] = []
    for ejercicio in ejercicios:
        contable = contables.get(ejercicio)
        fiscal = fiscales.get(ejercicio)
        estado = derivar_estado(
            contable.estado if contable is not None else None,
            fiscal.is_closed if fiscal is not None else None,
        )
        fila: EjercicioResuelto = {
            "ejercicio": ejercicio,
            "estado": estado,
            "es_actual": es_actual(ejercicio, hoy),
            "n_asientos": await contar_asientos(
                db, empresa_id=empresa_id, ejercicio=ejercicio
            ),
            # Solo es seleccionable si existe como ejercicio contable Y esta
            # abierto. Un ano que solo aparece en `FiscalYear` no admite asientos,
            # asi que no se ofrece para escribir en el.
            "es_seleccionable": estado != CERRADO and contable is not None,
        }
        filas.append(fila)
    return filas


def elegir_activo(
    filas: list[EjercicioResuelto], solicitado: int | None, hoy: dt.date | None = None
) -> int | None:
    """Que ejercicio queda activo. Regla de research D3.

    1. Si el cliente envio uno, se usa **solo si existe, es de esta empresa y esta
       abierto**. Un ejercicio cerrado se rechaza, no se muestra.
    2. Si no hay ninguno, el ano en curso.
    3. Si el ano en curso no existe para esta empresa, el mas reciente que exista y
       este abierto, que es el caso de una empresa con solo anos pasados.
    4. Si no hay ninguno abierto, `None`: la capa de API lo comunica y se impide
       escribir, en lugar de asumir un ejercicio.
    """
    por_anio = {f["ejercicio"]: f for f in filas}
    if (
        solicitado is not None
        and solicitado in por_anio
        and por_anio[solicitado]["es_seleccionable"]
    ):
        return solicitado
    referencia = hoy or hoy_utc()
    actual = por_anio.get(referencia.year)
    if actual is not None and actual["es_seleccionable"]:
        return referencia.year
    seleccionables = [f["ejercicio"] for f in filas if f["es_seleccionable"]]
    if seleccionables:
        return max(seleccionables)
    return None
