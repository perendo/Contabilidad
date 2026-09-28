"""Modelos y bloqueo de periodos cerrados (SPEC-028 T010 + T015).

Cubre la unicidad de la clave natural `(empresa_id, ejercicio, tipo, periodo)`,
las FKs compuestas por `empresa_id` (constitucion III), la correlatividad de
`numero_solicitud` (constitucion IV) y el rechazo con 409 `periodo_cerrado` de
un asiento cuya fecha cae en un mes cerrado (FR-001).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from models.acct.fiscal_year import FiscalYear
from models.closing.cierre_ejercicio import CierreEjercicio, EstadoCierreEjercicio
from models.closing.periodo_cerrado import (
    ESTADOS_BLOQUEANTES,
    EstadoPeriodo,
    PeriodoCerrado,
    TipoPeriodo,
)
from models.closing.solicitud_reapertura import (
    EstadoSolicitud,
    SolicitudReapertura,
    TipoPeriodoReapertura,
)
from services.closing.errores import ClosingError
from services.closing.periodo import cerrar_periodo_intermedio
from services.closing.reglas_cierre import (
    meses_del_periodo,
    rango_periodo,
    validar_periodo_abierto,
)
from services.journal.entry_service import AsientoError
from tests.unit import closing_support as soporte

EMPRESA = soporte.A
OTRA = soporte.B
EJERCICIO = 2026


@pytest.fixture(autouse=True)
async def _empresa(db_session_factory):
    async with db_session_factory() as session:
        await soporte.empresa(session, EMPRESA)
        await soporte.empresa(session, OTRA)
        await session.commit()


# --- T010 · unicidad y constraints del modelo -----------------------------


async def test_clave_natural_unica_por_empresa_ejercicio_tipo_periodo(db_session):
    await soporte.cerrar_meses(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=[3]
    )
    db_session.add(
        PeriodoCerrado(
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            tipo=TipoPeriodo.MES,
            periodo=3,
            fecha_ini=date(EJERCICIO, 3, 1),
            fecha_fin=date(EJERCICIO, 3, 31),
            estado=EstadoPeriodo.cerrado,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_la_misma_clave_natural_en_otra_empresa_s_si_se_permite(db_session):
    """La unicidad incluye `empresa_id`: dos empresas cierran su mes 3."""
    await soporte.cerrar_meses(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=[3]
    )
    await soporte.cerrar_meses(
        db_session, empresa_id=OTRA, ejercicio=EJERCICIO, meses=[3]
    )
    a = await soporte.periodo(db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, numero=3)
    b = await soporte.periodo(db_session, empresa_id=OTRA, ejercicio=EJERCICIO, numero=3)
    assert a is not None and b is not None
    assert a.id != b.id


async def test_trimestre_y_mes_conviven_en_la_misma_clave_natural(db_session):
    """`tipo` forma parte de la clave: mes 3 y trimestre 4 no colisionan."""
    await soporte.cerrar_meses(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=[3]
    )
    await soporte.cerrar_meses(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=[4], tipo="TRIMESTRE"
    )
    mes = await soporte.periodo(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, numero=3
    )
    trimestre = await soporte.periodo(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, tipo="TRIMESTRE", numero=4
    )
    assert mes is not None and trimestre is not None
    assert mes.tipo is TipoPeriodo.MES
    assert trimestre.tipo is TipoPeriodo.TRIMESTRE
    assert trimestre.fecha_ini == date(EJERCICIO, 10, 1)
    assert trimestre.fecha_fin == date(EJERCICIO, 12, 31)


async def test_rango_derivado_del_calendario(db_session):
    fila = await soporte.cerrar_meses(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=[2]
    )
    periodo = fila[0]
    assert periodo.fecha_ini == date(EJERCICIO, 2, 1)
    assert periodo.fecha_fin == date(EJERCICIO, 2, 28)  # 2026 no es bisiesto


async def test_rango_de_trimestre_abre_enero_y_cierra_marzo(db_session):
    inicio, fin = rango_periodo(EJERCICIO, TipoPeriodo.TRIMESTRE, 1)
    assert inicio == date(EJERCICIO, 1, 1)
    assert fin == date(EJERCICIO, 3, 31)
    assert list(meses_del_periodo(TipoPeriodo.TRIMESTRE, 1)) == [1, 2, 3]
    assert list(meses_del_periodo(TipoPeriodo.MES, 5)) == [5]


@pytest.mark.parametrize(
    ("tipo", "periodo"),
    [("MES", 0), ("MES", 13), ("TRIMESTRE", 0), ("TRIMESTRE", 5), ("SEMANAL", 1)],
)
def test_rango_rechaza_periodos_fuera_de_rango(tipo: str, periodo: int) -> None:
    with pytest.raises(ClosingError) as exc:
        rango_periodo(EJERCICIO, tipo, periodo)
    assert exc.value.code in {"periodo_invalido", "tipo_periodo_invalido"}
    assert exc.value.status_code == 422


def test_estados_bloqueantes_excluyen_el_periodo_reabierto() -> None:
    assert EstadoPeriodo.cerrado in ESTADOS_BLOQUEANTES
    assert EstadoPeriodo.cerrado_ajustado in ESTADOS_BLOQUEANTES
    assert EstadoPeriodo.reabierto_ajuste not in ESTADOS_BLOQUEANTES
    assert EstadoPeriodo.abierto not in ESTADOS_BLOQUEANTES


async def test_cierre_unico_por_empresa_y_ejercicio(db_session):
    db_session.add(
        CierreEjercicio(
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            estado=EstadoCierreEjercicio.completado,
            fecha_cierre=date(EJERCICIO, 12, 31),
            resultado_ejercicio=Decimal("0.0000"),
        )
    )
    await db_session.flush()
    db_session.add(
        CierreEjercicio(
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            estado=EstadoCierreEjercicio.completado,
            fecha_cierre=date(EJERCICIO, 12, 31),
            resultado_ejercicio=Decimal("0.0000"),
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_motivo_de_reapertura_obligatorio_en_la_tabla(db_session):
    periodo = (
        await soporte.cerrar_meses(
            db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=[3]
        )
    )[0]
    db_session.add(
        SolicitudReapertura(
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            numero_solicitud=1,
            periodo_id=periodo.id,
            tipo_periodo=TipoPeriodoReapertura.MES,
            periodo=3,
            motivo="   ",
            estado=EstadoSolicitud.pendiente,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_reapertura_anual_no_puede_colgar_de_un_periodo(db_session):
    db_session.add(
        SolicitudReapertura(
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            numero_solicitud=1,
            periodo_id=uuid.uuid4(),
            tipo_periodo=TipoPeriodoReapertura.ANUAL,
            motivo="Error en el cierre anual",
            estado=EstadoSolicitud.pendiente,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_fk_de_solicitud_rechaza_el_periodo_de_otra_empresa(db_session):
    """Constitucion III: un periodo de A no se puede enlazar desde B."""
    periodo = (
        await soporte.cerrar_meses(
            db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=[3]
        )
    )[0]
    db_session.add(
        SolicitudReapertura(
            empresa_id=OTRA,
            ejercicio=EJERCICIO,
            numero_solicitud=1,
            periodo_id=periodo.id,
            tipo_periodo=TipoPeriodoReapertura.MES,
            periodo=3,
            motivo="Intento de cruce de tenant",
            estado=EstadoSolicitud.pendiente,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_numeracion_correlativa_de_solicitudes(db_session):
    """Constitucion IV: `numero_solicitud` correlativo por (empresa, ejercicio)."""
    from services.closing.secuencia import next_numero_solicitud

    assert await next_numero_solicitud(db_session, EMPRESA, EJERCICIO) == 1
    assert await next_numero_solicitud(db_session, EMPRESA, EJERCICIO) == 2
    # Otra empresa y otro ejercicio llevan su propia correlatividad.
    assert await next_numero_solicitud(db_session, OTRA, EJERCICIO) == 1
    assert await next_numero_solicitud(db_session, EMPRESA, EJERCICIO + 1) == 1


# --- T015 · el periodo cerrado bloquea la contabilizacion -------------------


async def test_mes_cerrado_rechaza_el_asiento_del_periodo(db_session):
    await soporte.cerrar_meses(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=[3]
    )
    with pytest.raises(AsientoError) as exc:
        await soporte.publicar_asiento(
            db_session,
            empresa_id=EMPRESA,
            fecha=date(EJERCICIO, 3, 15),
            lineas=[
                {"cuenta": "5720", "debe": "100.0000"},
                {"cuenta": "7000", "haber": "100.0000"},
            ],
        )
    assert exc.value.code == "periodo_cerrado"
    assert "MARZO" in exc.value.message.upper() or "MES 3" in exc.value.message.upper()


async def test_asiento_fuera_del_rango_cerrado_se_acepta(db_session):
    await soporte.cerrar_meses(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=[3]
    )
    asiento = await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 4, 15),
        lineas=[
            {"cuenta": "5720", "debe": "100.0000"},
            {"cuenta": "7000", "haber": "100.0000"},
        ],
    )
    assert asiento is not None


async def test_el_ultimo_dia_del_mes_cerrado_tambien_esta_bloqueado(db_session):
    await soporte.cerrar_meses(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=[3]
    )
    with pytest.raises(ClosingError) as exc:
        await validar_periodo_abierto(db_session, EMPRESA, date(EJERCICIO, 3, 31))
    assert exc.value.code == "periodo_cerrado"


async def test_el_primer_dia_del_mes_siguiente_no_esta_bloqueado(db_session):
    await soporte.cerrar_meses(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=[3]
    )
    await validar_periodo_abierto(db_session, EMPRESA, date(EJERCICIO, 4, 1))


async def test_trimestre_cerrado_bloquea_todo_su_rango(db_session):
    """Cerrar el trimestre 2 bloquea abril, mayo y junio completos."""
    await soporte.cerrar_meses(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=[2], tipo="TRIMESTRE"
    )
    for fecha in (date(EJERCICIO, 4, 1), date(EJERCICIO, 5, 14), date(EJERCICIO, 6, 30)):
        with pytest.raises(ClosingError) as exc:
            await validar_periodo_abierto(db_session, EMPRESA, fecha)
        assert exc.value.code == "periodo_cerrado"
    # El dia anterior y el siguiente siguen abiertos.
    await validar_periodo_abierto(db_session, EMPRESA, date(EJERCICIO, 3, 31))
    await validar_periodo_abierto(db_session, EMPRESA, date(EJERCICIO, 7, 1))


async def test_una_empresa_no_bloquea_los_periodos_de_otra(db_session):
    """Constitucion III: el bloqueo es por empresa, no global."""
    await soporte.cerrar_meses(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=[3]
    )
    asiento = await soporte.publicar_asiento(
        db_session,
        empresa_id=OTRA,
        fecha=date(EJERCICIO, 3, 15),
        lineas=[
            {"cuenta": "5720", "debe": "50.0000"},
            {"cuenta": "7000", "haber": "50.0000"},
        ],
    )
    assert asiento is not None


async def test_el_ejercicio_cerrado_sigue_bloqueando(db_session):
    await soporte.fiscal_year(db_session, empresa_id=EMPRESA, year=EJERCICIO, cerrado=True)
    with pytest.raises(AsientoError) as exc:
        await soporte.publicar_asiento(
            db_session,
            empresa_id=EMPRESA,
            fecha=date(EJERCICIO, 6, 1),
            lineas=[
                {"cuenta": "5720", "debe": "10.0000"},
                {"cuenta": "7000", "haber": "10.0000"},
            ],
        )
    assert exc.value.code == "ejercicio_cerrado"


async def test_periodo_cerrado_sobre_ejercicio_inexistente_no_se_crea(db_session):
    """Un ejercicio sin `FiscalYear` sigue admitiendo contabilidad (SPEC-002)."""
    await soporte.cerrar_meses(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=[3]
    )
    assert await db_session.get(FiscalYear, 1) is None
    asiento = await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 7, 1),
        lineas=[
            {"cuenta": "5720", "debe": "10.0000"},
            {"cuenta": "7000", "haber": "10.0000"},
        ],
    )
    assert asiento is not None


async def test_no_se_puede_cerrar_dos_veces_el_mismo_mes(db_session):
    await soporte.cerrar_meses(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=[3]
    )
    with pytest.raises(ClosingError) as exc:
        await cerrar_periodo_intermedio(
            db_session,
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            tipo="MES",
            periodo=3,
            actor="test",
        )
    assert exc.value.code == "periodo_ya_cerrado"
    assert exc.value.status_code == 409


async def test_no_se_puede_cerrar_un_mes_cubierto_por_un_trimestre(db_session):
    await soporte.cerrar_meses(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=[1], tipo="TRIMESTRE"
    )
    with pytest.raises(ClosingError) as exc:
        await cerrar_periodo_intermedio(
            db_session,
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            tipo="MES",
            periodo=2,
            actor="test",
        )
    assert exc.value.code == "periodo_cubierto"
