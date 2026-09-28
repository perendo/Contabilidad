"""Aislamiento multi-tenant de los cierres (SPEC-028 T011, T017, T030, T043, T053).

Constitucion III: toda consulta y mutacion de `PeriodoCerrado`, `BalanzaPeriodo`,
`CierreEjercicio` y `SolicitudReapertura` filtra por la empresa activa. Ninguna
peticion acepta `empresa_id` en el path ni en el body, y el recurso de una
empresa devuelve 404 (nunca 403) desde la otra.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from models.closing.cierre_ejercicio import CierreEjercicio
from models.closing.periodo_cerrado import PeriodoCerrado, TipoPeriodo
from models.closing.solicitud_reapertura import SolicitudReapertura
from services.closing.cierre_anual import obtener_cierre_anual
from services.closing.periodo import (
    calendario_periodos,
    listar_periodos,
    obtener_balanza_periodo,
)
from services.closing.reapertura import (
    aprobar_reapertura,
    listar_solicitudes,
    marcar_reabierta,
    obtener_solicitud,
    solicitar_reapertura,
)

A = 10
B = 20
EJERCICIO = 2026
MESES = list(range(1, 13))


@pytest.fixture(autouse=True)
async def _empresas(db_session_factory):
    from tests.unit import closing_support as soporte

    async with db_session_factory() as session:
        await soporte.empresa(session, A)
        await soporte.empresa(session, B)
        await session.commit()


def _ventas(importe: str = "1000.0000") -> list[dict]:
    return [
        {"cuenta": "7000", "haber": importe},
        {"cuenta": "4300", "debe": importe},
    ]


# --- T011 · modelos: una empresa no ve los datos de la otra ----------------


async def test_una_empresa_no_ve_los_periodos_de_la_otra(db_session) -> None:
    from tests.unit import closing_support as soporte

    await soporte.cerrar_meses(db_session, empresa_id=A, ejercicio=EJERCICIO, meses=[3])
    listado = await listar_periodos(db_session, empresa_id=B, ejercicio=EJERCICIO)
    assert listado["total"] == 0
    assert listado["items"] == []
    assert await soporte.periodo(db_session, empresa_id=B, ejercicio=EJERCICIO, numero=3) is None


async def test_la_balanza_de_otra_empresa_da_404(db_session) -> None:
    from tests.unit import closing_support as soporte

    await soporte.cerrar_meses(db_session, empresa_id=A, ejercicio=EJERCICIO, meses=[3])
    periodo_a = await soporte.periodo(db_session, empresa_id=A, ejercicio=EJERCICIO, numero=3)
    assert periodo_a is not None
    from services.closing.errores import ClosingError

    with pytest.raises(ClosingError) as exc:
        await obtener_balanza_periodo(
            db_session, empresa_id=B, periodo_id=periodo_a.id
        )
    assert exc.value.status_code == 404


async def test_el_bloqueo_de_periodo_no_alcanza_a_la_otra_empresa(db_session) -> None:
    """El trigger y el servicio filtran por `empresa_id`: B puede asentar igual."""
    from tests.unit import closing_support as soporte

    await soporte.cerrar_meses(db_session, empresa_id=A, ejercicio=EJERCICIO, meses=[3])
    asiento = await soporte.publicar_asiento(
        db_session,
        empresa_id=B,
        fecha=date(EJERCICIO, 3, 15),
        lineas=_ventas("500.0000"),
    )
    assert asiento is not None


async def test_el_calendario_de_B_no_refleja_el_cierre_de_A(db_session) -> None:
    from tests.unit import closing_support as soporte

    await soporte.cerrar_meses(db_session, empresa_id=A, ejercicio=EJERCICIO, meses=[3])
    items_b = await calendario_periodos(
        db_session, empresa_id=B, ejercicio=EJERCICIO, tipo=TipoPeriodo.MES
    )
    marzo_b = next(item for item in items_b if item["periodo"] == 3)
    assert marzo_b["estado"] == "abierto"
    assert marzo_b["periodo_id"] is None


# --- T017 · US1 por HTTP ---------------------------------------------------


def test_cerrar_el_mes_3_bloquea_solo_a_la_empresa_que_lo_cierra(closing_client) -> None:
    cierres = closing_client
    assert cierres.get("/api/v1/cierres/intermedios", empresa_id=A).json()["total"] == 0
    respuesta = cierres.post(
        "/api/v1/cierres/intermedios",
        json={"ejercicio": EJERCICIO, "tipo": "MES", "periodo": 3},
        empresa_id=A,
    )
    assert respuesta.status_code == 201
    assert respuesta.json()["estado"] == "cerrado"
    listado_a = cierres.get("/api/v1/cierres/intermedios", empresa_id=A).json()
    assert listado_a["total"] == 1
    listado_b = cierres.get("/api/v1/cierres/intermedios", empresa_id=B).json()
    assert listado_b["total"] == 0
    # B puede cerrar su propio mes 3 sin conflicto.
    propio = cierres.post(
        "/api/v1/cierres/intermedios",
        json={"ejercicio": EJERCICIO, "tipo": "MES", "periodo": 3},
        empresa_id=B,
    )
    assert propio.status_code == 201
    assert propio.json()["periodo_id"] != respuesta.json()["periodo_id"]


def test_la_balanza_de_A_no_se_abre_desde_B(closing_client) -> None:
    cierres = closing_client
    creado = cierres.post(
        "/api/v1/cierres/intermedios",
        json={"ejercicio": EJERCICIO, "tipo": "MES", "periodo": 3},
        empresa_id=A,
    )
    periodo_a = creado.json()["periodo_id"]
    assert cierres.get(
        f"/api/v1/cierres/intermedios/{periodo_a}/balanza", empresa_id=B
    ).status_code == 404
    assert cierres.get(
        f"/api/v1/cierres/intermedios/{periodo_a}/balanza", empresa_id=A
    ).status_code == 200


# --- T030 · US2 por HTTP ---------------------------------------------------


def test_el_cierre_anual_de_A_no_lo_ve_B(closing_client) -> None:
    cierres = closing_client
    for empresa in (A, B):
        cierres.asiento(
            empresa,
            "2026-03-31",
            [
                {"cuenta": "1110", "haber": "17000.0000"},
                {"cuenta": "2100", "debe": "17000.0000"},
            ],
        )
        cierres.asiento(
            empresa,
            "2026-03-31",
            [
                {"cuenta": "7000", "haber": "10000.0000"},
                {"cuenta": "4300", "debe": "10000.0000"},
            ],
        )
        cierres.asiento(
            empresa,
            "2026-06-30",
            [
                {"cuenta": "6000", "debe": "7000.0000"},
                {"cuenta": "4300", "haber": "7000.0000"},
            ],
        )
        cierres.cerrar_periodos(empresa, EJERCICIO, range(1, 13))
    creado = cierres.post("/api/v1/cierres/anual", json={"ejercicio": EJERCICIO}, empresa_id=A)
    assert creado.status_code == 201
    assert cierres.get(f"/api/v1/cierres/anual/{EJERCICIO}", empresa_id=B).status_code == 404
    assert cierres.get(f"/api/v1/cierres/anual/{EJERCICIO}", empresa_id=A).status_code == 200
    # B puede cerrar su propio ejercicio sin conflicto.
    propio = cierres.post("/api/v1/cierres/anual", json={"ejercicio": EJERCICIO}, empresa_id=B)
    assert propio.status_code == 201
    assert propio.json()["cierre_id"] != creado.json()["cierre_id"]


# --- T043 · US3 por HTTP ---------------------------------------------------


def test_la_solicitud_de_A_no_se_ve_ni_se_aprueba_desde_B(closing_client) -> None:
    cierres = closing_client
    creado = cierres.post(
        "/api/v1/cierres/intermedios",
        json={"ejercicio": EJERCICIO, "tipo": "MES", "periodo": 3},
        empresa_id=A,
    )
    periodo_a = creado.json()["periodo_id"]
    solicitud = cierres.post(
        "/api/v1/cierres/reaperturas",
        json={
            "ejercicio": EJERCICIO,
            "tipo_periodo": "MES",
            "periodo": 3,
            "motivo": "Error de imputacion",
        },
        empresa_id=A,
    )
    assert solicitud.status_code == 201
    solicitud_id = solicitud.json()["solicitud_id"]
    assert cierres.get("/api/v1/cierres/reaperturas", empresa_id=B).json()["total"] == 0
    assert cierres.get("/api/v1/cierres/reaperturas", empresa_id=A).json()["total"] == 1
    assert cierres.get(f"/api/v1/cierres/reaperturas/{solicitud_id}", empresa_id=B).status_code == 404
    assert (
        cierres.post(f"/api/v1/cierres/reaperturas/{solicitud_id}/aprobar", empresa_id=B).status_code
        == 404
    )
    assert (
        cierres.post(f"/api/v1/cierres/reaperturas/{solicitud_id}/aprobar", empresa_id=A).status_code
        == 200
    )
    assert periodo_a  # el periodo existe en A


# --- T053 · recorrido completo de extremo a extremo -----------------------


def test_recorrido_completo_aislado_entre_empresas(closing_client) -> None:
    """A cierra, reabre y rectifica; B no ve nada de A y opera por su cuenta."""
    cierres = closing_client
    # 1) A cierra el mes 3 con movimientos.
    assert (
        cierres.post(
            "/api/v1/cierres/intermedios",
            json={"ejercicio": EJERCICIO, "tipo": "MES", "periodo": 3},
            empresa_id=A,
        ).status_code
        == 201
    )
    # 2) B no lo ve.
    assert cierres.get("/api/v1/cierres/intermedios", empresa_id=B).json()["total"] == 0
    # 3) A solicita y ejecuta la reapertura.
    solicitud = cierres.post(
        "/api/v1/cierres/reaperturas",
        json={
            "ejercicio": EJERCICIO,
            "tipo_periodo": "MES",
            "periodo": 3,
            "motivo": "Ajuste posterior a una factura",
        },
        empresa_id=A,
    ).json()
    assert (
        cierres.post(
            f"/api/v1/cierres/reaperturas/{solicitud['solicitud_id']}/aprobar", empresa_id=A
        ).status_code
        == 200
    )
    # 4) B sigue sin ver la solicitud de A.
    assert cierres.get("/api/v1/cierres/reaperturas", empresa_id=B).json()["total"] == 0
    # 5) A rectifica; B no puede hacerlo.
    rectificativo = cierres.asiento(
        A,
        "2026-03-20",
        [
            {"cuenta": "7000", "haber": "500.0000"},
            {"cuenta": "4300", "debe": "500.0000"},
        ],
        tipo="ADJUSTMENT",
    )
    rectificativo = str(rectificativo)
    assert (
        cierres.post(
            f"/api/v1/cierres/reaperturas/{solicitud['solicitud_id']}/rectificar",
            json={"asiento_id": rectificativo},
            empresa_id=B,
        ).status_code
        == 404
    )
    assert (
        cierres.post(
            f"/api/v1/cierres/reaperturas/{solicitud['solicitud_id']}/rectificar",
            json={"asiento_id": rectificativo},
            empresa_id=A,
        ).status_code
        == 200
    )
    # 6) B opera con normalidad en sus propios periodos.
    assert (
        cierres.post(
            "/api/v1/cierres/intermedios",
            json={"ejercicio": EJERCICIO, "tipo": "MES", "periodo": 3},
            empresa_id=B,
        ).status_code
        == 201
    )


async def test_las_tablas_de_closing_no_mezclan_empresas(db_session) -> None:
    """Ninguna consulta sin `empresa_id` debe devolver filas de la otra empresa."""
    from sqlalchemy import select

    from tests.unit import closing_support as soporte

    await soporte.cerrar_meses(db_session, empresa_id=A, ejercicio=EJERCICIO, meses=[3])
    await soporte.cerrar_meses(db_session, empresa_id=B, ejercicio=EJERCICIO, meses=[3])
    for empresa in (A, B):
        periodos = (
            await db_session.scalars(
                select(PeriodoCerrado).where(PeriodoCerrado.empresa_id == empresa)
            )
        ).all()
        assert len(periodos) == 1
        assert all(p.empresa_id == empresa for p in periodos)


async def test_el_cierre_anual_de_una_empresa_no_se_registra_en_la_otra(db_session) -> None:
    from tests.unit import closing_support as soporte

    await soporte.fiscal_year(db_session, empresa_id=A, year=EJERCICIO)
    await soporte.cerrar_meses(db_session, empresa_id=A, ejercicio=EJERCICIO, meses=MESES)
    from services.closing.cierre_anual import generar_cierre_anual

    resultado = await generar_cierre_anual(
        db_session, empresa_id=A, ejercicio=EJERCICIO, actor="test", abrir_siguiente=False
    )
    assert resultado["cierre"].empresa_id == A
    from services.closing.errores import ClosingError

    with pytest.raises(ClosingError) as exc:
        await obtener_cierre_anual(db_session, empresa_id=B, ejercicio=EJERCICIO)
    assert exc.value.status_code == 404
    assert await db_session.get(CierreEjercicio, resultado["cierre"].id) is not None


async def test_la_solicitud_de_A_no_se_aprueba_desde_B_a_nivel_de_servicio(db_session) -> None:
    from services.closing.errores import ClosingError
    from tests.unit import closing_support as soporte

    await soporte.cerrar_meses(db_session, empresa_id=A, ejercicio=EJERCICIO, meses=[3])
    fila = await solicitar_reapertura(
        db_session,
        empresa_id=A,
        ejercicio=EJERCICIO,
        tipo_periodo="MES",
        periodo=3,
        motivo="Error",
        actor="test",
    )
    with pytest.raises(ClosingError) as exc:
        await marcar_reabierta(
            db_session, empresa_id=B, solicitud_id=fila.id, actor="responsable"
        )
    assert exc.value.status_code == 404
    assert fila.estado.value == "pendiente"


def test_los_importes_de_la_balanza_viajan_como_cadenas(closing_client) -> None:
    """Contrato: importes como `Decimal` de 4 decimales, nunca `float`."""
    cierres = closing_client
    cierres.asiento(
        A,
        "2026-03-10",
        [
            {"cuenta": "7000", "haber": "1234.5000"},
            {"cuenta": "4300", "debe": "1234.5000"},
        ],
    )
    creado = cierres.post(
        "/api/v1/cierres/intermedios",
        json={"ejercicio": EJERCICIO, "tipo": "MES", "periodo": 3},
        empresa_id=A,
    ).json()
    assert creado["balanza"]["total_debe"] == "1234.5000"
    assert creado["balanza"]["total_haber"] == "1234.5000"
    assert creado["balanza"]["cuadra"] is True
    assert isinstance(creado["resultado_provisional"], str)
    balanza = cierres.get(
        f"/api/v1/cierres/intermedios/{creado['periodo_id']}/balanza", empresa_id=A
    ).json()
    for linea in balanza["lineas"]:
        for campo in ("debe", "haber", "saldo"):
            assert isinstance(linea[campo], str)
            assert len(linea[campo].split(".")[1]) == 4
    assert Decimal(balanza["total_debe"]) == Decimal(balanza["total_haber"])


def test_la_solicitud_registra_motivo_usuario_y_numero(closing_client) -> None:
    cierres = closing_client
    for mes in (3, 4):
        assert (
            cierres.post(
                "/api/v1/cierres/intermedios",
                json={"ejercicio": EJERCICIO, "tipo": "MES", "periodo": mes},
                empresa_id=A,
            ).status_code
            == 201
        )
    primera = cierres.post(
        "/api/v1/cierres/reaperturas",
        json={
            "ejercicio": EJERCICIO,
            "tipo_periodo": "MES",
            "periodo": 3,
            "motivo": "Error de imputacion",
        },
        empresa_id=A,
    ).json()
    segunda = cierres.post(
        "/api/v1/cierres/reaperturas",
        json={
            "ejercicio": EJERCICIO,
            "tipo_periodo": "MES",
            "periodo": 4,
            "motivo": "Otro ajuste",
        },
        empresa_id=A,
    ).json()
    assert primera["numero_solicitud"] == 1
    assert segunda["numero_solicitud"] == 2
    detalle = cierres.get(
        f"/api/v1/cierres/reaperturas/{primera['solicitud_id']}", empresa_id=A
    ).json()
    assert detalle["motivo"] == "Error de imputacion"
    assert detalle["usuario_solicitante"] == "api"
    assert detalle["fecha_solicitud"]


async def test_listar_solicitudes_ignora_a_la_otra_empresa(db_session) -> None:
    from sqlalchemy import select

    from tests.unit import closing_support as soporte

    await soporte.cerrar_meses(db_session, empresa_id=A, ejercicio=EJERCICIO, meses=[3])
    await solicitar_reapertura(
        db_session,
        empresa_id=A,
        ejercicio=EJERCICIO,
        tipo_periodo="MES",
        periodo=3,
        motivo="Error",
        actor="test",
    )
    listado = await listar_solicitudes(db_session, empresa_id=B)
    assert listado["total"] == 0
    assert (
        await db_session.scalar(
            select(SolicitudReapertura).where(SolicitudReapertura.empresa_id == A)
        )
        is not None
    )


async def test_aprobar_una_solicitud_inexistente_devuelve_404(db_session) -> None:
    import uuid

    from services.closing.errores import ClosingError

    with pytest.raises(ClosingError) as exc:
        await aprobar_reapertura(
            db_session, empresa_id=A, solicitud_id=uuid.uuid4(), actor="responsable"
        )
    assert exc.value.status_code == 404
    with pytest.raises(ClosingError) as exc:
        await obtener_solicitud(db_session, empresa_id=A, solicitud_id=uuid.uuid4())
    assert exc.value.status_code == 404
