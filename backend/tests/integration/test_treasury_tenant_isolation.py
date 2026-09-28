"""Cross-tenant isolation tests (T013).

A tenant can never observe or reach another tenant's treasury data through any
query: direct get by id, listing, or attempts to reference foreign rows.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.treasury import (
    BlobFichero,
    CondicionProntoPago,
    FormatoRemesa,
    MandatoSepa,
    ReciboEstado,
    ReciboRemesa,
    Remesa,
    RemesaEstado,
    TipoAdeudo,
)


async def _remesa_de(
    session: AsyncSession, empresa_id: int, importe: str = "150.0000", numero: int = 1
) -> Remesa:
    remesa = Remesa(
        empresa_id=empresa_id,
        ejercicio=2026,
        numero_remesa=numero,
        formato=FormatoRemesa.SEPA_DD,
        tipo_adeudo=TipoAdeudo.CORE,
        importe_total=Decimal(importe),
        estado=RemesaEstado.borrador,
    )
    session.add(remesa)
    await session.flush()
    return remesa


async def _recibo_de(session: AsyncSession, remesa: Remesa, vencimiento_id: uuid.UUID) -> ReciboRemesa:
    recibo = ReciboRemesa(
        empresa_id=remesa.empresa_id,
        remesa_id=remesa.id,
        vencimiento_id=vencimiento_id,
        recibo_num="R-0001",
        tercero_id=uuid.uuid4(),
        iban="ES9121000418450200051332",
        importe=Decimal("150.0000"),
        fecha_cargo=date(2026, 10, 10),
        estado=ReciboEstado.pendiente,
    )
    session.add(recibo)
    await session.flush()
    return recibo


async def test_remesa_de_empresa_a_no_visible_desde_b(db_session):
    remesa_a = await _remesa_de(db_session, empresa_id=1)
    await db_session.commit()

    vista = await db_session.scalar(
        select(Remesa).where(
            Remesa.empresa_id == 2,
            Remesa.id == remesa_a.id,
        )
    )
    assert vista is None

    listado_b = (
        await db_session.scalars(select(Remesa).where(Remesa.empresa_id == 2))
    ).all()
    assert listado_b == []

    listado_a = (
        await db_session.scalars(select(Remesa).where(Remesa.empresa_id == 1))
    ).all()
    assert [r.id for r in listado_a] == [remesa_a.id]


async def test_recibo_de_empresa_a_no_visible_desde_b(db_session):
    remesa_a = await _remesa_de(db_session, empresa_id=1)
    recibo = await _recibo_de(db_session, remesa_a, uuid.uuid4())
    await db_session.commit()

    assert (
        await db_session.scalar(
            select(ReciboRemesa).where(
                ReciboRemesa.empresa_id == 2,
                ReciboRemesa.id == recibo.id,
            )
        )
        is None
    )


async def test_contador_remesas_por_empresa_aislado(db_session):
    await _remesa_de(db_session, empresa_id=1, numero=1)
    await _remesa_de(db_session, empresa_id=1, numero=2)
    await _remesa_de(db_session, empresa_id=2, numero=1)
    await db_session.commit()

    conteo_a = await db_session.scalar(
        select(func.count()).select_from(Remesa).where(Remesa.empresa_id == 1)
    )
    conteo_b = await db_session.scalar(
        select(func.count()).select_from(Remesa).where(Remesa.empresa_id == 2)
    )
    assert conteo_a == 2
    assert conteo_b == 1


async def test_condicion_y_mandato_aislados(db_session):
    db_session.add_all(
        [
            CondicionProntoPago(
                empresa_id=1,
                tercero_id=uuid.uuid4(),
                plazo_dias=15,
                porcentaje=Decimal("2.50"),
                vigente=True,
            ),
            MandatoSepa(
                empresa_id=1,
                tercero_id=uuid.uuid4(),
                mandato_ref="MAND-A",
                fecha_firma=date(2026, 9, 1),
                tipo=TipoAdeudo.B2B,
                estado="firmado",
            ),
        ]
    )
    await db_session.commit()

    condicion_b = (
        await db_session.scalars(select(CondicionProntoPago).where(CondicionProntoPago.empresa_id == 2))
    ).all()
    mandato_b = (
        await db_session.scalars(select(MandatoSepa).where(MandatoSepa.empresa_id == 2))
    ).all()
    assert condicion_b == []
    assert mandato_b == []


async def test_tercero_blob_aislado(db_session):
    blob = BlobFichero(
        empresa_id=1,
        tipo="remesa_sepa",
        contenido=b"<Document/>",
        sha256="a" * 64,
    )
    db_session.add(blob)
    await db_session.commit()

    desde_b = await db_session.scalar(
        select(BlobFichero).where(BlobFichero.empresa_id == 2, BlobFichero.id == blob.id)
    )
    assert desde_b is None