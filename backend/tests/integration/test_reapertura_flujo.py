"""Flujo completo de la reapertura controlada (SPEC-028 T050, US3/FR-004).

Quickstart Scenario 4: cerrar el mes, solicitar la reapertura, aprobarla, crear
el asiento rectificativo por el motor de SPEC-002 y cerrar el ajuste. El periodo
vuelve a quedar bloqueado con `n_reaperturas` incrementado y el asiento original
intacto.
"""

from __future__ import annotations

import pytest

A = 10
B = 20
EJERCICIO = 2026


def _ventas(importe: str = "1000.0000") -> list[dict]:
    return [
        {"cuenta": "7000", "haber": importe},
        {"cuenta": "4300", "debe": importe},
    ]


def _cerrar(cierres, empresa: int = A, mes: int = 3):
    return cierres.post(
        "/api/v1/cierres/intermedios",
        json={"ejercicio": EJERCICIO, "tipo": "MES", "periodo": mes},
        empresa_id=empresa,
    ).json()


def _solicitar(cierres, mes: int = 3, empresa: int = A, motivo: str = "Error de imputacion"):
    return cierres.post(
        "/api/v1/cierres/reaperturas",
        json={
            "ejercicio": EJERCICIO,
            "tipo_periodo": "MES",
            "periodo": mes,
            "motivo": motivo,
        },
        empresa_id=empresa,
    )


def test_scenario_4_ciclo_completo_de_reapertura(closing_client) -> None:
    from services.journal.entry_service import AsientoError

    cierres = closing_client
    original = cierres.asiento(A, "2026-03-10", _ventas("1000.0000"))
    periodo = _cerrar(cierres)
    assert periodo["estado"] == "cerrado"

    # 1) Solicitud con justificacion.
    solicitud = _solicitar(cierres)
    assert solicitud.status_code == 201
    cuerpo = solicitud.json()
    assert cuerpo["estado"] == "pendiente"
    assert cuerpo["numero_solicitud"] == 1
    assert cuerpo["tipo_periodo"] == "MES"
    assert cuerpo["periodo"] == 3

    # 2) Aprobacion: el periodo se desbloquea temporalmente.
    aprobado = cierres.post(
        f"/api/v1/cierres/reaperturas/{cuerpo['solicitud_id']}/aprobar", empresa_id=A
    )
    assert aprobado.status_code == 200
    assert aprobado.json()["estado"] == "reabierta"
    assert aprobado.json()["aprobada_por"] == "api"
    assert aprobado.json()["fecha_aprobacion"]

    # 3) El asiento rectificativo se asienta durante el periodo reabierto.
    rectificativo = cierres.asiento(
        A, "2026-03-20", _ventas("1000.0000"), concepto="Anulacion", tipo="REVERSAL"
    )

    # 4) Cerrar el ajuste: re-cierre automatico del periodo.
    cerrado = cierres.post(
        f"/api/v1/cierres/reaperturas/{cuerpo['solicitud_id']}/rectificar",
        json={"asiento_id": str(rectificativo)},
        empresa_id=A,
    )
    assert cerrado.status_code == 200
    final = cerrado.json()
    assert final["estado"] == "cerrada"
    assert final["asiento_rectificacion_id"] == str(rectificativo)
    assert final["fecha_cierre_efectivo"]

    # El periodo vuelve a bloquearse y el contador sube.
    detalle = cierres.get(
        f"/api/v1/cierres/reaperturas/{cuerpo['solicitud_id']}", empresa_id=A
    ).json()
    assert detalle["periodo_cerrado"]["estado"] == "cerrado_ajustado"
    assert detalle["periodo_cerrado"]["n_reaperturas"] == 1
    assert detalle["asiento_rectificacion_id"] == str(rectificativo)

    # Un asiento posterior en el mismo mes vuelve a rechazarse.
    with pytest.raises(AsientoError) as exc:
        cierres.asiento(A, "2026-03-25", _ventas("1.0000"))
    assert exc.value.code == "periodo_cerrado"

    # El asiento original sigue intacto.
    async def _firma(session):
        from sqlalchemy import select

        from models.acct.journal import JournalEntry, JournalEntryLine

        entrada = await session.get(JournalEntry, original)
        filas = (
            await session.execute(
                select(JournalEntryLine.debe, JournalEntryLine.haber).where(
                    JournalEntryLine.journal_entry_id == original
                )
            )
        ).all()
        debe = sum((float(fila[0]) for fila in filas), 0.0)
        haber = sum((float(fila[1]) for fila in filas), 0.0)
        return entrada.concepto, entrada.estado.value, debe, haber

    firma = cierres.run(cierres.consultar(_firma))
    assert firma[1] == "POSTED"
    assert firma[2] == 1000.0
    assert firma[3] == 1000.0


def test_doble_solicitud_para_el_mismo_periodo_devuelve_409(closing_client) -> None:
    cierres = closing_client
    _cerrar(cierres)
    assert _solicitar(cierres).status_code == 201
    segunda = _solicitar(cierres, motivo="Segundo intento")
    assert segunda.status_code == 409
    assert segunda.json()["detail"]["code"] == "solicitud_activa"


def test_rectificar_sin_asiento_devuelve_404(closing_client) -> None:
    import uuid

    cierres = closing_client
    _cerrar(cierres)
    solicitud = _solicitar(cierres).json()
    cierres.post(
        f"/api/v1/cierres/reaperturas/{solicitud['solicitud_id']}/aprobar", empresa_id=A
    )
    respuesta = cierres.post(
        f"/api/v1/cierres/reaperturas/{solicitud['solicitud_id']}/rectificar",
        json={"asiento_id": str(uuid.uuid4())},
        empresa_id=A,
    )
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"]["code"] == "asiento_no_encontrado"


def test_rectificar_sin_aprobacion_devuelve_409(closing_client) -> None:
    import uuid

    cierres = closing_client
    _cerrar(cierres)
    solicitud = _solicitar(cierres).json()
    respuesta = cierres.post(
        f"/api/v1/cierres/reaperturas/{solicitud['solicitud_id']}/rectificar",
        json={"asiento_id": str(uuid.uuid4())},
        empresa_id=A,
    )
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["code"] == "solicitud_no_reabierta"


def test_rectificar_dos_veces_devuelve_409(closing_client) -> None:
    cierres = closing_client
    _cerrar(cierres)
    solicitud = _solicitar(cierres).json()
    cierres.post(
        f"/api/v1/cierres/reaperturas/{solicitud['solicitud_id']}/aprobar", empresa_id=A
    )
    rectificativo = cierres.asiento(
        A, "2026-03-20", _ventas("100.0000"), tipo="ADJUSTMENT"
    )
    primero = cierres.post(
        f"/api/v1/cierres/reaperturas/{solicitud['solicitud_id']}/rectificar",
        json={"asiento_id": str(rectificativo)},
        empresa_id=A,
    )
    assert primero.status_code == 200
    segundo = cierres.post(
        f"/api/v1/cierres/reaperturas/{solicitud['solicitud_id']}/rectificar",
        json={"asiento_id": str(rectificativo)},
        empresa_id=A,
    )
    assert segundo.status_code == 409
    assert segundo.json()["detail"]["code"] == "solicitud_no_reabierta"


def test_rechazar_mantiene_el_periodo_bloqueado(closing_client) -> None:
    from services.journal.entry_service import AsientoError

    cierres = closing_client
    _cerrar(cierres)
    solicitud = _solicitar(cierres).json()
    respuesta = cierres.post(
        f"/api/v1/cierres/reaperturas/{solicitud['solicitud_id']}/rechazar", empresa_id=A
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "rechazada"
    with pytest.raises(AsientoError) as exc:
        cierres.asiento(A, "2026-03-20", _ventas("1.0000"))
    assert exc.value.code == "periodo_cerrado"


def test_rechazar_una_solicitud_ya_aprobada_devuelve_409(closing_client) -> None:
    cierres = closing_client
    _cerrar(cierres)
    solicitud = _solicitar(cierres).json()
    assert (
        cierres.post(
            f"/api/v1/cierres/reaperturas/{solicitud['solicitud_id']}/aprobar", empresa_id=A
        ).status_code
        == 200
    )
    repetido = cierres.post(
        f"/api/v1/cierres/reaperturas/{solicitud['solicitud_id']}/aprobar", empresa_id=A
    )
    assert repetido.status_code == 409
    assert repetido.json()["detail"]["code"] == "estado_invalido"


def test_sin_motivo_devuelve_422(closing_client) -> None:
    """Quickstart Scenario 5."""
    cierres = closing_client
    _cerrar(cierres)
    respuesta = cierres.post(
        "/api/v1/cierres/reaperturas",
        json={"ejercicio": EJERCICIO, "tipo_periodo": "MES", "periodo": 3},
        empresa_id=A,
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "justificacion_requerida"


def test_reapertura_de_un_periodo_abierto_devuelve_404(closing_client) -> None:
    cierres = closing_client
    respuesta = _solicitar(cierres, mes=5)
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"]["code"] == "periodo_no_cerrado"


def test_reapertura_con_ejercicio_formulado_devuelve_409(closing_client) -> None:
    """SC-004: cero reaperturas con cuentas anuales formuladas."""
    from datetime import date as _date

    cierres = closing_client
    _cerrar(cierres)

    async def _formular(session):
        from models.reporting.formulacion import (
            FormulacionCuentasAnuales,
            FormulacionEstado,
        )

        session.add(
            FormulacionCuentasAnuales(
                empresa_id=A,
                ejercicio=EJERCICIO,
                numero_formulacion=1,
                fecha_formulacion=_date(EJERCICIO, 12, 31),
                contenido_hash="0" * 64,
                estado=FormulacionEstado.formulada,
                snapshot={},
            )
        )

    cierres.run(cierres.mutar(_formular))
    respuesta = _solicitar(cierres)
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]["code"] == "ejercicio_legalizado"


def test_reapertura_con_is_contabilizado_exige_nota_de_impacto(closing_client) -> None:
    from decimal import Decimal

    cierres = closing_client
    _cerrar(cierres)

    async def _contabilizar_is(session):
        from models.fiscal.calculo_is import CalculoIS, EstadoCalculoIS

        session.add(
            CalculoIS(
                empresa_id=A,
                ejercicio=EJERCICIO,
                resultado_contable=Decimal("1000.0000"),
                base_imponible=Decimal("1000.0000"),
                tipo_impositivo=Decimal("25.00"),
                cuota_integra=Decimal("250.0000"),
                cuota_liquida=Decimal("250.0000"),
                provisional=False,
                estado=EstadoCalculoIS.contabilizado,
            )
        )

    cierres.run(cierres.mutar(_contabilizar_is))
    sin_nota = _solicitar(cierres)
    assert sin_nota.status_code == 409
    assert sin_nota.json()["detail"]["code"] == "is_liquidado"

    con_nota = cierres.post(
        "/api/v1/cierres/reaperturas",
        json={
            "ejercicio": EJERCICIO,
            "tipo_periodo": "MES",
            "periodo": 3,
            "motivo": "Ajuste posterior al IS",
            "nota_impacto": "El IS provisional se recalculara",
        },
        empresa_id=A,
    )
    assert con_nota.status_code == 201


def test_reaperta_el_ejercicio_tras_el_cierre_anual(closing_client) -> None:
    """US3 sobre el cierre anual: el `CierreEjercicio` pasa a reapertura_pendiente."""
    from datetime import date as _date
    from decimal import Decimal

    from sqlalchemy import select

    from models.closing.cierre_ejercicio import CierreEjercicio, EstadoCierreEjercicio

    cierres = closing_client
    cierres.marcar_cerrado(A, EJERCICIO)

    async def _registrar_cierre(session):
        session.add(
            CierreEjercicio(
                empresa_id=A,
                ejercicio=EJERCICIO,
                estado=EstadoCierreEjercicio.completado,
                fecha_cierre=_date(EJERCICIO, 12, 31),
                resultado_ejercicio=Decimal("0.0000"),
            )
        )

    async def _estado_cierre(session):
        fila = await session.scalar(
            select(CierreEjercicio).where(
                CierreEjercicio.empresa_id == A,
                CierreEjercicio.ejercicio == EJERCICIO,
            )
        )
        return fila.estado

    cierres.run(cierres.mutar(_registrar_cierre))
    assert cierres.run(cierres.consultar(_estado_cierre)) is EstadoCierreEjercicio.completado

    respuesta = cierres.post(
        "/api/v1/cierres/reaperturas",
        json={
            "ejercicio": EJERCICIO,
            "tipo_periodo": "ANUAL",
            "motivo": "Error en el asiento de regularizacion",
        },
        empresa_id=A,
    )
    assert respuesta.status_code == 201
    assert respuesta.json()["tipo_periodo"] == "ANUAL"
    assert (
        cierres.run(cierres.consultar(_estado_cierre))
        is EstadoCierreEjercicio.reapertura_pendiente
    )


def test_el_listado_de_solicitudes_filtra(closing_client) -> None:
    cierres = closing_client
    for mes in (3, 4):
        _cerrar(cierres, mes=mes)
    primera = _solicitar(cierres, mes=3).json()
    segunda = _solicitar(cierres, mes=4, motivo="Otro").json()
    cierres.post(
        f"/api/v1/cierres/reaperturas/{primera['solicitud_id']}/aprobar", empresa_id=A
    )
    cierres.post(
        f"/api/v1/cierres/reaperturas/{segunda['solicitud_id']}/rechazar", empresa_id=A
    )
    todas = cierres.get("/api/v1/cierres/reaperturas", empresa_id=A).json()
    assert todas["total"] == 2
    pendientes = cierres.get("/api/v1/cierres/reaperturas", empresa_id=A, estado="pendiente").json()
    assert pendientes["total"] == 0
    reabierta = cierres.get("/api/v1/cierres/reaperturas", empresa_id=A, estado="reabierta").json()
    assert reabierta["total"] == 1
    por_mes = cierres.get("/api/v1/cierres/reaperturas", empresa_id=A, tipo_periodo="MES").json()
    assert por_mes["total"] == 2
    assert cierres.get("/api/v1/cierres/reaperturas", empresa_id=A, ejercicio=2025).json()["total"] == 0


def test_rbac_solo_admin_aprueba_las_reaperturas(closing_client) -> None:
    """SPEC-015: `aprobar` es una operacion exclusiva de ADMIN.

    La matriz base concede a ACCOUNTANT `ver/crear/editar/baja` y a READ_ONLY
    solo `ver`, asi que el rol contable puede solicitar la reapertura pero no
    desbloquear el periodo: esa es la separacion de responsabilidades que exige
    FR-003 ("un usuario autorizado").
    """
    cierres = closing_client
    _cerrar(cierres, mes=3)
    _cerrar(cierres, mes=4)
    solicitud = _solicitar(cierres, mes=3).json()
    cuerpo = {
        "ejercicio": EJERCICIO,
        "tipo_periodo": "MES",
        "periodo": 3,
        "motivo": "Intento no autorizado",
    }
    # READ_ONLY no puede ni siquiera solicitar.
    assert (
        cierres.post(
            "/api/v1/cierres/reaperturas", json=cuerpo, empresa_id=A, token_key="readonly"
        ).status_code
        == 403
    )
    assert (
        cierres.post(
            f"/api/v1/cierres/reaperturas/{solicitud['solicitud_id']}/aprobar",
            empresa_id=A,
            token_key="readonly",
        ).status_code
        == 403
    )
    # ACCOUNTANT puede solicitar, pero no aprobar.
    assert (
        cierres.post(
            "/api/v1/cierres/reaperturas",
            json={**cuerpo, "periodo": 4, "motivo": "Segunda solicitud"},
            empresa_id=A,
            token_key="accountant",
        ).status_code
        == 201
    )
    assert (
        cierres.post(
            f"/api/v1/cierres/reaperturas/{solicitud['solicitud_id']}/aprobar",
            empresa_id=A,
            token_key="accountant",
        ).status_code
        == 403
    )
    # ADMIN aprueba y ejecuta la reapertura.
    assert (
        cierres.post(
            f"/api/v1/cierres/reaperturas/{solicitud['solicitud_id']}/aprobar",
            empresa_id=A,
            token_key="admin",
        ).status_code
        == 200
    )
