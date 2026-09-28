from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from models.ar.tercero import Tercero
from models.audit.audit_log import AuditLog
from models.fiscal.liquidacion_retenciones import LiquidacionRetenciones
from models.fiscal.retencion import RetencionPeriodo, TipoRetencion
from services.fiscal.modelo_190_gen import (
    descargar_modelo_190,
    generar_modelo_190,
    listar_modelos_190,
)


async def _crear_anual(session, api, empresa_id: int = 10):
    segundo = Tercero(
        empresa_id=empresa_id,
        nombre="Segundo perceptor",
        nif="B12345674",
        es_cliente=False,
        es_proveedor=True,
    )
    session.add(segundo)
    await session.flush()
    tercero_a = api.terceros[empresa_id]["con_nif"]
    filas_por_trimestre = {
        1: (
            (tercero_a, "1000.0000", "15.00", "150.0000"),
            (segundo.id, "500.0000", "21.00", "105.0000"),
        ),
        2: ((tercero_a, "2000.0000", "15.00", "300.0000"),),
        3: ((tercero_a, "3000.0000", "19.00", "570.0000"),),
        4: (
            (tercero_a, "4000.0000", "19.00", "760.0000"),
            (segundo.id, "1500.0000", "21.00", "315.0000"),
        ),
    }
    for trimestre, filas in filas_por_trimestre.items():
        liquidacion = LiquidacionRetenciones(
            empresa_id=empresa_id,
            ejercicio=2025,
            trimestre=trimestre,
            periodo=f"2025-Q{trimestre}",
            total_base_retenciones=sum(
                (Decimal(fila[1]) for fila in filas), Decimal("0.0000")
            ),
            total_retenciones=sum(
                (Decimal(fila[3]) for fila in filas), Decimal("0.0000")
            ),
            n_perceptores=len({fila[0] for fila in filas}),
        )
        session.add(liquidacion)
        await session.flush()
        for tercero_id, base, tasa, retencion in filas:
            session.add(
                RetencionPeriodo(
                    empresa_id=empresa_id,
                    liquidacion_retenciones_id=liquidacion.id,
                    tercero_id=tercero_id,
                    nif="",
                    nombre="Perceptor actual",
                    tipo_retencion=TipoRetencion.IRPF_PROFESIONALES,
                    base_imponible=Decimal(base),
                    tipo_porcentaje=Decimal(tasa),
                    retencion_practicada=Decimal(retencion),
                    facturas=[],
                )
            )
    await session.flush()
    return await generar_modelo_190(
        session,
        empresa_id=empresa_id,
        ejercicio=2025,
        actor="test@example.test",
        ip="127.0.0.1",
    )


def test_modelo_190_completo_y_descarga(retenciones_client):
    api = retenciones_client
    modelo = api.run(api.mutar(lambda session: _crear_anual(session, api)))

    assert modelo.n_perceptores == 2
    assert modelo.contenido["totales_ejercicio"]["total_perceptores"] == 2
    assert modelo.contenido["totales_ejercicio"]["total_base_retenciones"] == "12000.0000"
    assert modelo.contenido["totales"]["total_retenciones_anual"] == "2200.0000"
    assert len(modelo.contenido["detalle_perceptores"]) == 3

    async def _listar(session):
        return await listar_modelos_190(
            session, empresa_id=10, ejercicio=2025, pagina=1, tamano=1
        )

    listados, total = api.run(api.consultar(_listar))
    assert total == 1
    assert len(listados) == 1
    assert listados[0].id == modelo.id

    contenido, tipo, nombre = api.run(
        api.consultar(
            lambda session: descargar_modelo_190(
                session, empresa_id=10, modelo_190_id=modelo.id
            )
        )
    )
    assert contenido.startswith("\ufeffbloque;campo;valor\n")
    assert "total_retenciones_anual" in contenido
    assert tipo == "text/csv; charset=utf-8"
    assert nombre == f"modelo-190-{modelo.id}.csv"

    async def _auditoria(session):
        return await session.scalar(
            select(AuditLog).where(
                AuditLog.empresa_id == 10,
                AuditLog.operacion == "GENERAR_MODELO_190",
                AuditLog.entidad_id == str(modelo.id),
            )
        )

    auditoria = api.run(api.consultar(_auditoria))
    assert auditoria is not None
    assert modelo.hash_contenido in auditoria.payload
