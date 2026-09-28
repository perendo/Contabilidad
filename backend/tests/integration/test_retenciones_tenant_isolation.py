from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.fiscal.liquidacion_retenciones import LiquidacionRetenciones
from models.fiscal.modelo_111 import Modelo111
from models.fiscal.modelo_115 import Modelo115
from models.fiscal.modelo_190 import Modelo190
from models.fiscal.retencion import RetencionPeriodo, TipoRetencion


async def _crear_datos(session: AsyncSession, api, empresa_id: int) -> dict[str, str]:
    tercero_id = api.terceros[empresa_id]["con_nif"]
    liquidacion = LiquidacionRetenciones(
        empresa_id=empresa_id,
        ejercicio=2025,
        trimestre=3,
        periodo="2025-Q3",
        total_base_retenciones=Decimal("1000.0000"),
        total_retenciones=Decimal("150.0000"),
        n_perceptores=1,
    )
    session.add(liquidacion)
    await session.flush()
    retencion = RetencionPeriodo(
        empresa_id=empresa_id,
        liquidacion_retenciones_id=liquidacion.id,
        tercero_id=tercero_id,
        nif="12345678Z",
        nombre=f"Perceptor {empresa_id}",
        tipo_retencion=TipoRetencion.IRPF_PROFESIONALES,
        base_imponible=Decimal("1000.0000"),
        tipo_porcentaje=Decimal("15.00"),
        retencion_practicada=Decimal("150.0000"),
        facturas=[],
    )
    modelo_111 = Modelo111(
        empresa_id=empresa_id,
        liquidacion_retenciones_id=liquidacion.id,
        ejercicio=2025,
        trimestre=3,
        contenido={"bloque": 1},
        hash_contenido="a" * 64,
    )
    modelo_115 = Modelo115(
        empresa_id=empresa_id,
        liquidacion_retenciones_id=liquidacion.id,
        ejercicio=2025,
        trimestre=3,
        contenido={"bloque": 1},
        hash_contenido="b" * 64,
    )
    modelo_190 = Modelo190(
        empresa_id=empresa_id,
        ejercicio=2025,
        contenido={"bloque": 1},
        hash_contenido="c" * 64,
        n_perceptores=1,
    )
    session.add_all([retencion, modelo_111, modelo_115, modelo_190])
    await session.flush()
    return {
        "liquidacion": str(liquidacion.id),
        "retencion": str(retencion.id),
        "modelo_111": str(modelo_111.id),
        "modelo_115": str(modelo_115.id),
        "modelo_190": str(modelo_190.id),
    }


async def _ids_visibles(
    session: AsyncSession, empresa_id: int, ids: dict[str, str]
) -> dict[str, list[str]]:
    liquidaciones = (
        await session.scalars(
            select(LiquidacionRetenciones).where(
                LiquidacionRetenciones.empresa_id == empresa_id,
                LiquidacionRetenciones.id == uuid.UUID(ids["liquidacion"]),
            )
        )
    ).all()
    retenciones = (
        await session.scalars(
            select(RetencionPeriodo).where(
                RetencionPeriodo.empresa_id == empresa_id,
                RetencionPeriodo.id == uuid.UUID(ids["retencion"]),
            )
        )
    ).all()
    modelos_111 = (
        await session.scalars(
            select(Modelo111).where(
                Modelo111.empresa_id == empresa_id,
                Modelo111.id == uuid.UUID(ids["modelo_111"]),
            )
        )
    ).all()
    modelos_115 = (
        await session.scalars(
            select(Modelo115).where(
                Modelo115.empresa_id == empresa_id,
                Modelo115.id == uuid.UUID(ids["modelo_115"]),
            )
        )
    ).all()
    modelos_190 = (
        await session.scalars(
            select(Modelo190).where(
                Modelo190.empresa_id == empresa_id,
                Modelo190.id == uuid.UUID(ids["modelo_190"]),
            )
        )
    ).all()
    return {
        "liquidaciones": [str(item.id) for item in liquidaciones],
        "retenciones": [str(item.id) for item in retenciones],
        "modelos_111": [str(item.id) for item in modelos_111],
        "modelos_115": [str(item.id) for item in modelos_115],
        "modelos_190": [str(item.id) for item in modelos_190],
    }


def test_liquidacion_y_soportes_no_visibles_para_otra_empresa(
    retenciones_client,
) -> None:
    api = retenciones_client
    ids = api.run(api.mutar(lambda session: _crear_datos(session, api, 10)))
    visibles_a = api.run(
        api.consultar(lambda session: _ids_visibles(session, 10, ids))
    )
    visibles_b = api.run(
        api.consultar(lambda session: _ids_visibles(session, 20, ids))
    )
    assert visibles_a == {
        "liquidaciones": [ids["liquidacion"]],
        "retenciones": [ids["retencion"]],
        "modelos_111": [ids["modelo_111"]],
        "modelos_115": [ids["modelo_115"]],
        "modelos_190": [ids["modelo_190"]],
    }
    assert visibles_b == {
        "liquidaciones": [],
        "retenciones": [],
        "modelos_111": [],
        "modelos_115": [],
        "modelos_190": [],
    }


def test_mismo_trimestre_puede_existir_en_empresa_distinta(
    retenciones_client,
) -> None:
    api = retenciones_client
    api.run(api.mutar(lambda session: _crear_datos(session, api, 10)))

    async def _crear_b(session: AsyncSession) -> str:
        liquidacion = LiquidacionRetenciones(
            empresa_id=20,
            ejercicio=2025,
            trimestre=3,
            periodo="2025-Q3",
            total_base_retenciones=Decimal("2000.0000"),
            total_retenciones=Decimal("300.0000"),
            n_perceptores=1,
        )
        session.add(liquidacion)
        await session.flush()
        return str(liquidacion.id)

    id_b = api.run(api.mutar(_crear_b))
    assert id_b
    visibles_b = api.run(
        api.consultar(
            lambda session: _ids_visibles(
                session,
                20,
                {
                    "liquidacion": id_b,
                    "retencion": "00000000-0000-0000-0000-000000000000",
                    "modelo_111": "00000000-0000-0000-0000-000000000000",
                    "modelo_115": "00000000-0000-0000-0000-000000000000",
                    "modelo_190": "00000000-0000-0000-0000-000000000000",
                },
            )
        )
    )
    assert visibles_b["liquidaciones"] == [id_b]
