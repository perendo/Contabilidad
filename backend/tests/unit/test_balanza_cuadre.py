"""Cuadre del balance de comprobacion del periodo (SPEC-028 T014 + T016).

Research D1/D3: el cierre intermedio NO crea asientos. Estos tests comprueban
que `total_debe == total_haber` exactamente en `Decimal`, que la suma de las
lineas reproduce los totales, que un periodo sin movimientos cierra a cero sin
anomalia, y que el diario queda intacto tras el cierre (T016).
"""

from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryLine
from models.closing.balanza_periodo import BalanzaPeriodo, BalanzaPeriodoLinea
from services.cashflow.utils import c4
from services.closing.balanza import huella_snapshot, leer_balanza
from services.closing.periodo import cerrar_periodo_intermedio, obtener_balanza_periodo
from tests.unit import closing_support as soporte

EMPRESA = soporte.A
EJERCICIO = 2026


@pytest.fixture(autouse=True)
async def _empresa(db_session_factory):
    async with db_session_factory() as session:
        await soporte.empresa(session, EMPRESA)
        await session.commit()


async def _cerrar(session, mes: int = 3, tipo: str = "MES", ejercicio: int = EJERCICIO):
    return await cerrar_periodo_intermedio(
        session,
        empresa_id=EMPRESA,
        ejercicio=ejercicio,
        tipo=tipo,
        periodo=mes,
        actor="test",
    )


def _contable(ejercicio: int, dia: int, importe: str = "1000.0000") -> list[dict]:
    return [
        {"cuenta": "7000", "haber": importe, "detail": "Ventas"},
        {"cuenta": "5720", "debe": importe, "detail": "Cobro"},
    ]


# --- T014 · cuadre estricto en Decimal -------------------------------------


async def test_total_debe_igual_a_total_haber(db_session) -> None:
    await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 3, 10),
        lineas=_contable(EJERCICIO, 10),
    )
    resultado = await _cerrar(db_session)
    balanza = resultado["balanza"]
    assert balanza.total_debe == balanza.total_haber
    assert balanza.total_debe == Decimal("1000.0000")
    assert balanza.n_lineas == 2


async def test_la_suma_de_las_lineas_reproduce_los_totales(db_session) -> None:
    for indice, fecha in enumerate((3, 15, 22), start=1):
        await soporte.publicar_asiento(
            db_session,
            empresa_id=EMPRESA,
            fecha=date(EJERCICIO, 3, fecha),
            lineas=_contable(EJERCICIO, fecha, f"{100 * indice}.0000"),
        )
    resultado = await _cerrar(db_session)
    balanza = resultado["balanza"]
    suma_debe = c4(sum((linea.debe for linea in resultado["lineas"]), Decimal(0)))
    suma_haber = c4(sum((linea.haber for linea in resultado["lineas"]), Decimal(0)))
    assert suma_debe == balanza.total_debe == Decimal("600.0000")
    assert suma_haber == balanza.total_haber == Decimal("600.0000")


async def test_el_saldo_de_cada_linea_es_debe_menos_haber(db_session) -> None:
    await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 3, 5),
        lineas=[
            {"cuenta": "5720", "debe": "300.0000"},
            {"cuenta": "7000", "haber": "300.0000"},
        ],
    )
    await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 3, 20),
        lineas=[
            {"cuenta": "5720", "haber": "120.5000"},
            {"cuenta": "6000", "debe": "120.5000"},
        ],
    )
    resultado = await _cerrar(db_session)
    por_codigo = {linea.codigo: linea for linea in resultado["lineas"]}
    assert por_codigo["5720"].debe == Decimal("300.0000")
    assert por_codigo["5720"].haber == Decimal("120.5000")
    assert por_codigo["5720"].saldo == Decimal("179.5000")
    for linea in resultado["lineas"]:
        assert linea.saldo == c4(linea.debe - linea.haber)


async def test_periodo_sin_movimientos_cierra_a_cero_sin_anomalia(db_session) -> None:
    """Quickstart Scenario 2: trimestre sin movimiento -> 0 == 0."""
    resultado = await _cerrar(db_session, mes=2, tipo="TRIMESTRE")
    balanza = resultado["balanza"]
    assert balanza.total_debe == balanza.total_haber == Decimal("0.0000")
    assert balanza.n_lineas == 0
    assert resultado["lineas"] == []


async def test_una_linea_solo_con_debe_o_solo_con_haber_es_valida(db_session) -> None:
    """La linea de balanza es una suma, no un apunte: un lado puede ser cero."""
    await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 3, 8),
        lineas=[
            {"cuenta": "4300", "debe": "500.0000"},
            {"cuenta": "7000", "haber": "500.0000"},
        ],
    )
    resultado = await _cerrar(db_session)
    por_codigo = {linea.codigo: linea for linea in resultado["lineas"]}
    assert por_codigo["4300"].haber == Decimal("0.0000")
    assert por_codigo["4300"].saldo == Decimal("500.0000")
    assert por_codigo["7000"].debe == Decimal("0.0000")


async def test_resultado_provisional_de_grupos_6_y_7(db_session) -> None:
    """Research D4: el resultado del periodo se deriva de los grupos 6/7."""
    await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 3, 9),
        lineas=[
            {"cuenta": "7000", "haber": "2000.0000"},
            {"cuenta": "6000", "debe": "500.0000"},
            {"cuenta": "5720", "debe": "1500.0000"},
        ],
    )
    resultado = await _cerrar(db_session)
    # S(6) - S(7) = 500 - 2000 = -1500 (perdidas)
    assert resultado["balanza"].resultado_provisional == Decimal("-1500.0000")


async def test_la_balanza_solo_agrega_el_rango_del_periodo(db_session) -> None:
    await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 2, 28),
        lineas=_contable(EJERCICIO, 28, "50.0000"),
    )
    await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 3, 28),
        lineas=_contable(EJERCICIO, 28, "70.0000"),
    )
    await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 4, 2),
        lineas=_contable(EJERCICIO, 2, "90.0000"),
    )
    resultado = await _cerrar(db_session)
    assert resultado["balanza"].total_debe == Decimal("70.0000")


async def test_los_borradores_no_entran_en_la_balanza(db_session) -> None:
    from services.journal.entry_service import crear_borrador

    mapa = await soporte.cuentas(db_session, EMPRESA)
    await crear_borrador(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 3, 12),
        concepto="Borrador sin asentar",
        lineas=[
            {"account_id": mapa["5720"], "debit": "999.0000", "credit": "0"},
            {"account_id": mapa["7000"], "debit": "0", "credit": "999.0000"},
        ],
        actor="test",
    )
    resultado = await _cerrar(db_session)
    assert resultado["balanza"].total_debe == Decimal("0.0000")


async def test_la_balanza_trae_codigo_nombre_y_nivel_del_plan(db_session) -> None:
    await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 3, 3),
        lineas=_contable(EJERCICIO, 3),
    )
    resultado = await _cerrar(db_session)
    por_codigo = {linea.codigo: linea for linea in resultado["lineas"]}
    assert por_codigo["7000"].nombre
    assert por_codigo["7000"].nivel == len("7000")


async def test_la_huella_sha256_es_estable_y_canonica(db_session) -> None:
    """Research D3: mismo contenido -> misma huella; el canon ordena por codigo."""
    await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 3, 3),
        lineas=_contable(EJERCICIO, 3),
    )
    primera = await _cerrar(db_session)
    await db_session.rollback()

    await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 3, 3),
        lineas=[
            {"cuenta": "7000", "haber": "1000.0000", "detail": "Ventas"},
            {"cuenta": "5720", "debe": "1000.0000", "detail": "Cobro"},
        ],
    )
    segunda = await _cerrar(db_session)
    assert primera["balanza"].sha256 == segunda["balanza"].sha256
    assert len(primera["balanza"].sha256) == 64


def test_la_huella_ordena_las_lineas_por_codigo() -> None:
    """El canon de `huella_snapshot` no depende del orden de entrada."""
    from models.closing.balanza_periodo import BalanzaPeriodoLinea as Linea

    def linea(codigo: str) -> Linea:
        return Linea(
            empresa_id=1,
            balanza_id=1,
            cuenta_id=1,
            codigo=codigo,
            nombre="n",
            nivel=4,
            debe=Decimal("1.0000"),
            haber=Decimal("0.0000"),
            saldo=Decimal("1.0000"),
        )

    a = huella_snapshot(2026, "MES", 3, date(2026, 3, 1), date(2026, 3, 31), [linea("7000"), linea("5720")], Decimal("2.0000"))
    b = huella_snapshot(2026, "MES", 3, date(2026, 3, 1), date(2026, 3, 31), [linea("5720"), linea("7000")], Decimal("2.0000"))
    assert a == b
    esperado = hashlib.sha256(
        b"2026|MES|3|2026-03-01|2026-03-31\n5720|1.0000|0.0000|1.0000\n7000|1.0000|0.0000|1.0000\nTOTAL|2.0000"
    ).hexdigest()
    assert a == esperado


async def test_el_balanza_se_puede_volver_a_leer(db_session) -> None:
    await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 3, 7),
        lineas=_contable(EJERCICIO, 7),
    )
    resultado = await _cerrar(db_session)
    periodo_id = resultado["periodo"].id
    cabecera, lineas = await obtener_balanza_periodo(
        db_session, empresa_id=EMPRESA, periodo_id=periodo_id
    )
    assert cabecera.id == resultado["balanza"].id
    assert len(lineas) == resultado["balanza"].n_lineas
    assert [linea.codigo for linea in lineas] == sorted(linea.codigo for linea in lineas)


async def test_periodo_sin_balanza_devuelve_404(db_session) -> None:
    import uuid

    from services.closing.errores import ClosingError as Error404

    with pytest.raises(Error404) as exc:
        await obtener_balanza_periodo(
            db_session, empresa_id=EMPRESA, periodo_id=uuid.uuid4()
        )
    assert exc.value.status_code == 404


# --- T016 · el cierre intermedio no muta el diario -------------------------


async def test_el_cierre_no_inserta_ni_modifica_asientos(db_session) -> None:
    """T016: el diario queda byte a byte igual tras cerrar el periodo."""
    await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 3, 11),
        lineas=_contable(EJERCICIO, 11),
    )
    await db_session.flush()

    async def _firmas(session) -> tuple[list, list]:
        entradas = (
            await session.execute(
                select(
                    JournalEntry.id,
                    JournalEntry.estado,
                    JournalEntry.numero_asiento,
                    JournalEntry.tipo,
                )
                .where(JournalEntry.empresa_id == EMPRESA)
                .order_by(JournalEntry.numero_asiento)
            )
        ).all()
        lineas = (
            await session.execute(
                select(JournalEntryLine.journal_entry_id, JournalEntryLine.debe, JournalEntryLine.haber)
                .where(JournalEntryLine.empresa_id == EMPRESA)
                .order_by(JournalEntryLine.journal_entry_id, JournalEntryLine.line_no)
            )
        ).all()
        return list(entradas), list(lineas)

    antes = await _firmas(db_session)
    await _cerrar(db_session)
    assert await _firmas(db_session) == antes

    total = await db_session.scalar(
        select(func.count()).select_from(JournalEntry).where(JournalEntry.empresa_id == EMPRESA)
    )
    assert total == 1


async def test_el_snapshot_no_toca_los_asientos_existentes(db_session) -> None:
    asiento_id = await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 3, 11),
        lineas=_contable(EJERCICIO, 11),
    )
    debe_antes, haber_antes = await soporte.saldos_asiento(
        db_session, empresa_id=EMPRESA, asiento_id=asiento_id
    )
    await _cerrar(db_session)
    debe_despues, haber_despues = await soporte.saldos_asiento(
        db_session, empresa_id=EMPRESA, asiento_id=asiento_id
    )
    assert (debe_antes, haber_antes) == (debe_despues, haber_despues) == (
        Decimal("1000.0000"),
        Decimal("1000.0000"),
    )
    estado = await db_session.scalar(
        select(JournalEntry.estado).where(JournalEntry.id == asiento_id)
    )
    assert estado is JournalEntryEstado.POSTED


# --- constitucion II · el snapshot es inmutable -----------------------------


async def test_la_balanza_rechaza_update(db_session) -> None:
    await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 3, 4),
        lineas=_contable(EJERCICIO, 4),
    )
    resultado = await _cerrar(db_session)
    cabecera = resultado["balanza"]
    with pytest.raises(IntegrityError) as exc:
        await db_session.execute(
            text("UPDATE balanza_periodo SET n_lineas = 99 WHERE id = :id"),
            {"id": cabecera.id.hex},
        )
    assert "inmutable" in str(exc.value).lower()
    await db_session.rollback()


async def test_la_balanza_rechaza_delete(db_session) -> None:
    await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 3, 4),
        lineas=_contable(EJERCICIO, 4),
    )
    resultado = await _cerrar(db_session)
    linea = resultado["lineas"][0]
    with pytest.raises(IntegrityError) as exc:
        await db_session.execute(
            text("DELETE FROM balanza_periodo_linea WHERE id = :id"),
            {"id": linea.id.hex},
        )
    assert "inmutable" in str(exc.value).lower()
    await db_session.rollback()


async def test_la_balanza_rechaza_borrar_la_cabecera(db_session) -> None:
    await soporte.publicar_asiento(
        db_session,
        empresa_id=EMPRESA,
        fecha=date(EJERCICIO, 3, 4),
        lineas=_contable(EJERCICIO, 4),
    )
    resultado = await _cerrar(db_session)
    with pytest.raises(IntegrityError) as exc:
        await db_session.execute(
            text("DELETE FROM balanza_periodo WHERE id = :id"),
            {"id": resultado["balanza"].id.hex},
        )
    assert "inmutable" in str(exc.value).lower()
    await db_session.rollback()


async def test_solo_hay_un_balanza_por_cierre(db_session) -> None:
    resultado = await _cerrar(db_session)
    periodo_id = resultado["periodo"].id
    db_session.add(
        BalanzaPeriodo(
            empresa_id=EMPRESA,
            periodo_id=periodo_id,
            ejercicio=EJERCICIO,
            fecha_ini=date(EJERCICIO, 3, 1),
            fecha_fin=date(EJERCICIO, 3, 31),
            n_lineas=0,
            total_debe=Decimal("0.0000"),
            total_haber=Decimal("0.0000"),
            resultado_provisional=Decimal("0.0000"),
            sha256="0" * 64,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_la_tabla_rechaza_un_balanza_descuadrado(db_session) -> None:
    """Constitucion I en el propio CHECK: `total_debe = total_haber`."""
    periodo_id = "b" * 32
    await db_session.execute(
        text(
            "INSERT INTO periodo_cerrado (id, empresa_id, ejercicio, tipo, periodo,"
            " fecha_ini, fecha_fin, estado, n_reaperturas)"
            " VALUES (:id, :empresa, :ejercicio, 'MES', 4, '2026-04-01', '2026-04-30',"
            " 'cerrado', 0)"
        ),
        {"id": periodo_id, "empresa": EMPRESA, "ejercicio": EJERCICIO},
    )
    with pytest.raises(IntegrityError) as exc:
        await db_session.execute(
            text(
                "INSERT INTO balanza_periodo (id, empresa_id, periodo_id, ejercicio,"
                " fecha_ini, fecha_fin, n_lineas, total_debe, total_haber,"
                " resultado_provisional, sha256)"
                " VALUES (:id, :empresa, :periodo, :ejercicio, '2026-04-01', '2026-04-30',"
                " 0, 100.0000, 90.0000, 0, :sha)"
            ),
            {
                "id": "c" * 32,
                "empresa": EMPRESA,
                "periodo": periodo_id,
                "ejercicio": EJERCICIO,
                "sha": "0" * 64,
            },
        )
    assert "cuadre" in str(exc.value).lower() or "check" in str(exc.value).lower()
    await db_session.rollback()


async def test_la_tabla_rechaza_lineas_de_balanza_con_importes_negativos(db_session) -> None:
    resultado = await _cerrar(db_session)
    with pytest.raises(IntegrityError) as exc:
        await db_session.execute(
            text(
                "INSERT INTO balanza_periodo_linea (id, empresa_id, balanza_id, cuenta_id,"
                " codigo, nombre, nivel, debe, haber, saldo)"
                " VALUES (:id, :empresa, :balanza, 999999, 'X1', 'Cuenta', 4,"
                " -5.0000, 0, -5.0000)"
            ),
            {
                "id": "e" * 32,
                "empresa": EMPRESA,
                "balanza": resultado["balanza"].id.hex,
            },
        )
    assert "debe" in str(exc.value).lower() or "check" in str(exc.value).lower()
    await db_session.rollback()


async def test_leer_balanza_devuelve_none_sin_snapshot(db_session) -> None:
    import uuid

    assert await leer_balanza(db_session, EMPRESA, uuid.uuid4()) is None


async def test_los_importes_de_la_balanza_son_numeric_18_4() -> None:
    for modelo, campos in (
        (BalanzaPeriodo, ("total_debe", "total_haber", "resultado_provisional")),
        (BalanzaPeriodoLinea, ("debe", "haber", "saldo")),
    ):
        for campo in campos:
            columna = modelo.__table__.columns[campo]
            assert str(columna.type) == "NUMERIC(18, 4)", f"{modelo.__name__}.{campo}"
