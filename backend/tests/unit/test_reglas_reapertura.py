"""Reglas de reapertura controlada (SPEC-028 T013, T038-T042).

Verifica FR-003, FR-005 y FR-006 ademas del impacto documentado de SPEC-010
(cuentas anuales formuladas) y SPEC-023 (IS contabilizado y definitivo).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from models.closing.periodo_cerrado import EstadoPeriodo
from models.closing.solicitud_reapertura import EstadoSolicitud, TipoPeriodoReapertura
from services.closing.errores import ClosingError
from services.closing.reapertura import (
    aprobar_reapertura,
    rechazar_reapertura,
    solicitar_reapertura,
)
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


async def _periodo_cerrado(session, empresa_id: int = EMPRESA, mes: int = 3) -> None:
    await soporte.cerrar_meses(
        session, empresa_id=empresa_id, ejercicio=EJERCICIO, meses=[mes]
    )


# --- T013 / T038 · FR-006 la justificacion es obligatoria ------------------


@pytest.mark.parametrize("motivo", [None, "", "   ", "\n\t"])
async def test_sin_motivo_se_rechaza_con_422(db_session, motivo: str | None) -> None:
    await _periodo_cerrado(db_session)
    with pytest.raises(ClosingError) as exc:
        await solicitar_reapertura(
            db_session,
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            tipo_periodo="MES",
            periodo=3,
            motivo=motivo,
            actor="test",
        )
    assert exc.value.code == "justificacion_requerida"
    assert exc.value.status_code == 422


async def test_el_motivo_se_guarda_normalizado(db_session) -> None:
    await _periodo_cerrado(db_session)
    fila = await solicitar_reapertura(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        tipo_periodo="MES",
        periodo=3,
        motivo="  Error de imputacion detectado  ",
        actor="test",
    )
    assert fila.motivo == "Error de imputacion detectado"
    assert fila.estado is EstadoSolicitud.pendiente
    assert fila.usuario_solicitante == "test"
    assert fila.numero_solicitud == 1


async def test_la_solicitud_registra_fecha_y_usuario(db_session) -> None:
    """FR-006 / SC-005: justificacion, usuario y fecha siempre presentes."""
    await _periodo_cerrado(db_session)
    fila = await solicitar_reapertura(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        tipo_periodo="MES",
        periodo=3,
        motivo="Ajuste legal pendiente",
        actor="responsable",
    )
    assert fila.fecha_solicitud is not None
    assert fila.aprobada_por is None
    assert fila.asiento_rectificacion_id is None
    assert fila.fecha_cierre_efectivo is None


# --- T039 · FR-005 una solicitud activa a la vez ---------------------------


@pytest.mark.parametrize(
    "estado", [EstadoSolicitud.pendiente, EstadoSolicitud.aprobada, EstadoSolicitud.reabierta]
)
async def test_segunda_solicitud_del_mismo_periodo_se_rechaza(
    db_session, estado: EstadoSolicitud
) -> None:
    await _periodo_cerrado(db_session)
    primera = await solicitar_reapertura(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        tipo_periodo="MES",
        periodo=3,
        motivo="Primera",
        actor="test",
    )
    primera.estado = estado
    await db_session.flush()
    with pytest.raises(ClosingError) as exc:
        await solicitar_reapertura(
            db_session,
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            tipo_periodo="MES",
            periodo=3,
            motivo="Segunda",
            actor="test",
        )
    assert exc.value.code == "solicitud_activa"
    assert exc.value.status_code == 409


async def test_una_solicitud_no_bloquea_otra_de_distinto_periodo(db_session) -> None:
    await soporte.cerrar_meses(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=[3, 4]
    )
    primera = await solicitar_reapertura(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        tipo_periodo="MES",
        periodo=3,
        motivo="Primera",
        actor="test",
    )
    segunda = await solicitar_reapertura(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        tipo_periodo="MES",
        periodo=4,
        motivo="Otro periodo",
        actor="test",
    )
    assert primera.numero_solicitud == 1
    assert segunda.numero_solicitud == 2


async def test_solicitudes_de_periodos_distintos_conviven(db_session) -> None:
    await soporte.cerrar_meses(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=[3, 4]
    )
    a = await solicitar_reapertura(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        tipo_periodo="MES",
        periodo=3,
        motivo="Marzo",
        actor="test",
    )
    b = await solicitar_reapertura(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        tipo_periodo="MES",
        periodo=4,
        motivo="Abril",
        actor="test",
    )
    assert a.periodo_id != b.periodo_id


async def test_no_se_solicita_la_reapertura_de_un_periodo_abierto(db_session) -> None:
    with pytest.raises(ClosingError) as exc:
        await solicitar_reapertura(
            db_session,
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            tipo_periodo="MES",
            periodo=5,
            motivo="No esta cerrado",
            actor="test",
        )
    assert exc.value.code == "periodo_no_cerrado"


async def test_periodo_inexistente_devuelve_404(db_session) -> None:
    with pytest.raises(ClosingError) as exc:
        await solicitar_reapertura(
            db_session,
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            tipo_periodo="MES",
            periodo=7,
            motivo="No existe",
            actor="test",
        )
    assert exc.value.status_code == 404


# --- T041 · SPEC-010 ejercicio formulado bloquea la reapertura -----------


async def test_ejercicio_con_cuentas_anuales_formuladas_se_rechaza(db_session) -> None:
    from models.reporting.formulacion import (
        FormulacionCuentasAnuales,
        FormulacionEstado,
    )

    await _periodo_cerrado(db_session)
    db_session.add(
        FormulacionCuentasAnuales(
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            numero_formulacion=1,
            fecha_formulacion=date(EJERCICIO, 12, 31),
            contenido_hash="0" * 64,
            estado=FormulacionEstado.formulada,
            snapshot={"balance": {}},
        )
    )
    await db_session.flush()
    with pytest.raises(ClosingError) as exc:
        await solicitar_reapertura(
            db_session,
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            tipo_periodo="MES",
            periodo=3,
            motivo="Error",
            actor="test",
        )
    assert exc.value.code == "ejercicio_legalizado"
    assert exc.value.status_code == 409


async def test_formulacion_anulada_no_bloquea(db_session) -> None:
    from models.reporting.formulacion import (
        FormulacionCuentasAnuales,
        FormulacionEstado,
    )

    await _periodo_cerrado(db_session)
    db_session.add(
        FormulacionCuentasAnuales(
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            numero_formulacion=1,
            fecha_formulacion=date(EJERCICIO, 12, 31),
            contenido_hash="0" * 64,
            estado=FormulacionEstado.anulada,
            snapshot={"balance": {}},
        )
    )
    await db_session.flush()
    fila = await solicitar_reapertura(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        tipo_periodo="MES",
        periodo=3,
        motivo="Reformulacion",
        actor="test",
    )
    assert fila.estado is EstadoSolicitud.pendiente


async def test_ejercicio_legalizado_se_rechaza(db_session) -> None:
    """SPEC-019: una legalizacion vigente es el equivalente externo del sellado."""
    from models.ngo.libros import Legalizacion

    await _periodo_cerrado(db_session)
    db_session.add(
        Legalizacion(
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            rango_asientos_desde=1,
            rango_asientos_hasta=10,
            total_asientos=10,
            huella="a" * 64,
            fecha_emision=date(EJERCICIO, 12, 31),
            valido=True,
        )
    )
    await db_session.flush()
    with pytest.raises(ClosingError) as exc:
        await solicitar_reapertura(
            db_session,
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            tipo_periodo="MES",
            periodo=3,
            motivo="Error",
            actor="test",
        )
    assert exc.value.code == "ejercicio_legalizado"


# --- T042 · SPEC-023 IS liquidado exige nota de impacto --------------------


def _calculo_is(empresa_id: int, *, estado: str, provisional: bool) -> object:
    from models.fiscal.calculo_is import CalculoIS, EstadoCalculoIS

    return CalculoIS(
        empresa_id=empresa_id,
        ejercicio=EJERCICIO,
        resultado_contable=Decimal("1000.0000"),
        base_imponible=Decimal("1000.0000"),
        tipo_impositivo=Decimal("25.00"),
        cuota_integra=Decimal("250.0000"),
        cuota_liquida=Decimal("250.0000"),
        provisional=provisional,
        estado=EstadoCalculoIS(estado),
    )


async def test_is_liquidado_sin_nota_de_impacto_se_rechaza(db_session) -> None:
    await _periodo_cerrado(db_session)
    db_session.add(_calculo_is(EMPRESA, estado="contabilizado", provisional=False))
    await db_session.flush()
    with pytest.raises(ClosingError) as exc:
        await solicitar_reapertura(
            db_session,
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            tipo_periodo="MES",
            periodo=3,
            motivo="Error",
            actor="test",
        )
    assert exc.value.code == "is_liquidado"
    assert exc.value.status_code == 409


async def test_is_liquidado_con_nota_de_impacto_se_acepta(db_session) -> None:
    await _periodo_cerrado(db_session)
    db_session.add(_calculo_is(EMPRESA, estado="contabilizado", provisional=False))
    await db_session.flush()
    fila = await solicitar_reapertura(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        tipo_periodo="MES",
        periodo=3,
        motivo="Ajuste posterior a la liquidacion del IS",
        nota_impacto="El IS provisional se recalculara; el definitivo se mantiene",
        actor="test",
    )
    assert fila.estado is EstadoSolicitud.pendiente
    assert fila.nota_impacto is not None


async def test_is_provisional_no_bloquea_la_reapertura(db_session) -> None:
    await _periodo_cerrado(db_session)
    db_session.add(_calculo_is(EMPRESA, estado="calculado", provisional=True))
    await db_session.flush()
    fila = await solicitar_reapertura(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        tipo_periodo="MES",
        periodo=3,
        motivo="Cierre intermedio normal",
        actor="test",
    )
    assert fila.estado is EstadoSolicitud.pendiente


# --- FR-005 / FR-003 · transiciones del flujo ------------------------------


async def test_aprobar_desbloquea_el_periodo_y_rechazar_lo_mantiene(db_session) -> None:
    await soporte.cerrar_meses(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, meses=[3, 4]
    )
    para_aprobar = await solicitar_reapertura(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        tipo_periodo="MES",
        periodo=3,
        motivo="Aprobar",
        actor="test",
    )
    await aprobar_reapertura(
        db_session,
        empresa_id=EMPRESA,
        solicitud_id=para_aprobar.id,
        actor="responsable",
    )
    periodo = await soporte.periodo(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, numero=3
    )
    assert periodo is not None
    assert periodo.estado is EstadoPeriodo.reabierto_ajuste

    para_rechazar = await solicitar_reapertura(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        tipo_periodo="MES",
        periodo=4,
        motivo="Rechazar",
        actor="test",
    )
    await rechazar_reapertura(
        db_session,
        empresa_id=EMPRESA,
        solicitud_id=para_rechazar.id,
        actor="responsable",
    )
    intacto = await soporte.periodo(
        db_session, empresa_id=EMPRESA, ejercicio=EJERCICIO, numero=4
    )
    assert intacto is not None
    assert intacto.estado is EstadoPeriodo.cerrado
    assert para_rechazar.estado is EstadoSolicitud.rechazada
    assert para_rechazar.aprobada_por == "responsable"
    assert para_rechazar.fecha_aprobacion is not None


async def test_no_se_aprueba_dos_veces_la_misma_solicitud(db_session) -> None:
    await _periodo_cerrado(db_session)
    fila = await solicitar_reapertura(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        tipo_periodo="MES",
        periodo=3,
        motivo="Error",
        actor="test",
    )
    await aprobar_reapertura(
        db_session, empresa_id=EMPRESA, solicitud_id=fila.id, actor="responsable"
    )
    with pytest.raises(ClosingError) as exc:
        await aprobar_reapertura(
            db_session, empresa_id=EMPRESA, solicitud_id=fila.id, actor="responsable"
        )
    assert exc.value.code == "estado_invalido"
    assert exc.value.status_code == 409


async def test_no_se_aprueba_una_solicitud_ya_rechazada(db_session) -> None:
    await _periodo_cerrado(db_session)
    fila = await solicitar_reapertura(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        tipo_periodo="MES",
        periodo=3,
        motivo="Error",
        actor="test",
    )
    await rechazar_reapertura(
        db_session, empresa_id=EMPRESA, solicitud_id=fila.id, actor="responsable"
    )
    with pytest.raises(ClosingError) as exc:
        await aprobar_reapertura(
            db_session, empresa_id=EMPRESA, solicitud_id=fila.id, actor="responsable"
        )
    assert exc.value.code == "estado_invalido"


async def test_solicitud_de_otra_empresa_no_se_ve(db_session) -> None:
    """Constitucion III: aprobar la solicitud de A desde B es 404."""
    await _periodo_cerrado(db_session)
    fila = await solicitar_reapertura(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        tipo_periodo="MES",
        periodo=3,
        motivo="Error",
        actor="test",
    )
    with pytest.raises(ClosingError) as exc:
        await aprobar_reapertura(
            db_session, empresa_id=OTRA, solicitud_id=fila.id, actor="responsable"
        )
    assert exc.value.status_code == 404


# --- reapertura del ejercicio completo (ANUAL) ------------------------------


async def test_reapertura_anual_exige_ejercicio_cerrado(db_session) -> None:
    with pytest.raises(ClosingError) as exc:
        await solicitar_reapertura(
            db_session,
            empresa_id=EMPRESA,
            ejercicio=EJERCICIO,
            tipo_periodo=TipoPeriodoReapertura.ANUAL,
            motivo="Error en el cierre",
            actor="test",
        )
    assert exc.value.code == "ejercicio_abierto"


async def test_reapertura_anual_requiere_numero_de_solicitud_sin_periodo(db_session) -> None:
    await soporte.fiscal_year(db_session, empresa_id=EMPRESA, year=EJERCICIO, cerrado=True)
    fila = await solicitar_reapertura(
        db_session,
        empresa_id=EMPRESA,
        ejercicio=EJERCICIO,
        tipo_periodo="ANUAL",
        motivo="Error en el asiento de regularizacion",
        actor="test",
    )
    assert fila.periodo_id is None
    assert fila.periodo is None
    assert fila.tipo_periodo is TipoPeriodoReapertura.ANUAL
