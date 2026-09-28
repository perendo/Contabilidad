"""Helpers compartidos de los tests de SPEC-029 (exportacion integral).

`sembrar_tenant` crea el dataset minimo que necesitan los bloques del catalogo:
empresa con PGC, terceros con subcuenta, serie, facturas de venta y compra,
asientos de dos ejercicios, un vencimiento y la configuracion SII. Los tests
integracion lo usan a traves de la fixture `export_client` de `conftest.py`.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.fiscal_year import FiscalYear
from models.ar.tercero import Tercero
from models.ar.tercero_subcuenta import TerceroSubcuenta, TipoSubcuenta
from models.ar.vencimiento import EstadoVencimiento, TipoVencimiento, Vencimiento
from models.export.config_sii import ConfigSii
from models.invoice.factura import Factura, FacturaEstado, FacturaTipo
from models.invoice.factura_linea import FacturaLinea
from models.invoice.serie_factura import SerieFactura
from services.export.bloques import Bloque
from services.export.recopilar import BloqueRecopilado

__all__ = [
    "CUENTAS",
    "asiento",
    "bloque_de_prueba",
    "cuenta_id",
    "factura",
    "sembrar_tenant",
    "tercero",
]

#: Cuentas apuntables del seed de SPEC-001 usadas por los asientos del test.
CUENTAS: dict[str, str] = {
    "cliente": "4300",
    "proveedor": "4000",
    "banco": "5720",
    "ventas": "7000",
    "compras": "6000",
    "iva_repercutido": "4700",
    "iva_soportado": "4720",
    "cobros": "5700",
    "resultado": "7900",
}


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


async def cuenta_id(db: AsyncSession, empresa_id: int, codigo: str) -> int:
    fila = await db.scalar(
        select(AccountPlan.id).where(
            AccountPlan.tenant_id == empresa_id, AccountPlan.code == codigo
        )
    )
    if fila is None:
        raise AssertionError(f"La cuenta {codigo} no existe en el PGC de {empresa_id}")
    return int(fila)


async def tercero(
    db: AsyncSession,
    empresa_id: int,
    nombre: str,
    nif: str,
    *,
    es_cliente: bool = True,
    es_proveedor: bool = False,
) -> Tercero:
    fila = Tercero(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        nombre=nombre,
        nif=nif,
        es_cliente=es_cliente,
        es_proveedor=es_proveedor,
    )
    db.add(fila)
    await db.flush()
    for tipo, prefijo, activo in (
        (TipoSubcuenta.CLIENTE, "430", es_cliente),
        (TipoSubcuenta.PROVEEDOR, "400", es_proveedor),
    ):
        if activo:
            db.add(
                TerceroSubcuenta(
                    id=uuid.uuid4(),
                    empresa_id=empresa_id,
                    tercero_id=fila.id,
                    tipo=tipo,
                    cuenta_codigo=f"{prefijo}{str(fila.id)[:4].upper()}",
                )
            )
    await db.flush()
    return fila


async def asiento(
    db: AsyncSession,
    *,
    empresa_id: int,
    fecha: date,
    lineas: list[tuple[str, Decimal, Decimal]],
    concepto: str = "Asiento de exportacion",
    estado: str = "POSTED",
    tipo: str = "GENERAL",
) -> uuid.UUID:
    """Asiento correlativo con sus lineas, sin pasar por el motor de SPEC-002.

    El fixture escribe filas directamente para no acoplar los tests de
    exportacion al servicio de asientos; el equilibrio se respeta igualmente
    (constitution I).
    """
    from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryLine

    ultimo = await db.scalar(
        select(JournalEntry.numero_asiento)
        .where(JournalEntry.empresa_id == empresa_id, JournalEntry.ejercicio == fecha.year)
        .order_by(JournalEntry.numero_asiento.desc())
        .limit(1)
    )
    entrada = JournalEntry(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        ejercicio=fecha.year,
        fecha=fecha,
        tipo=tipo,
        concepto=concepto,
        numero_asiento=(ultimo or 0) + 1,
        estado=JournalEntryEstado(estado),
        created_at=_ahora(),
    )
    db.add(entrada)
    await db.flush()
    total_debe = sum((Decimal(str(d)) for _, d, _ in lineas), Decimal(0))
    total_haber = sum((Decimal(str(h)) for _, _, h in lineas), Decimal(0))
    if total_debe != total_haber:
        raise AssertionError(
            f"Asiento descuadrado en el test: debe={total_debe} haber={total_haber}"
        )
    for indice, (cuenta, debe, haber) in enumerate(lineas, start=1):
        db.add(
            JournalEntryLine(
                id=uuid.uuid4(),
                empresa_id=empresa_id,
                journal_entry_id=entrada.id,
                account_id=await cuenta_id(db, empresa_id, cuenta),
                line_no=indice,
                cuenta=cuenta,
                debe=Decimal(str(debe)),
                haber=Decimal(str(haber)),
            )
        )
    await db.flush()
    return entrada.id


async def factura(
    db: AsyncSession,
    *,
    empresa_id: int,
    tercero_id: uuid.UUID,
    serie_id: uuid.UUID,
    ejercicio: int,
    numero: int,
    fecha: date,
    tipo: FacturaTipo,
    base: Decimal,
    iva: Decimal,
    total: Decimal,
    estado: FacturaEstado = FacturaEstado.emitida,
) -> Factura:
    fila = Factura(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        serie_id=serie_id,
        numero=numero,
        ejercicio=ejercicio,
        fecha=fecha,
        tipo=tipo,
        tercero_id=tercero_id,
        importe_base=base,
        importe_iva=iva,
        importe_total=total,
        estado=estado,
        created_at=_ahora(),
    )
    db.add(fila)
    await db.flush()
    db.add(
        FacturaLinea(
            id=uuid.uuid4(),
            empresa_id=empresa_id,
            factura_id=fila.id,
            line_no=1,
            descripcion="Linea de prueba",
            cantidad=Decimal(1),
            precio_unitario=base,
            base=base,
            tipo_iva=Decimal(21) if iva > 0 else Decimal(0),
            cuota_iva=iva,
        )
    )
    await db.flush()
    return fila


async def sembrar_tenant(
    db: AsyncSession,
    empresa_id: int,
    *,
    con_sii: bool = False,
    con_compras: bool = True,
    ejercicios: tuple[int, ...] = (2025, 2026),
) -> dict[str, Any]:
    """Dataset minimo de la empresa: PGC, fiscal year, terceros, facturas, asientos."""
    from services.acct.seed import seed_default_pgc

    await seed_default_pgc(db, empresa_id)
    for anio in ejercicios:
        db.add(
            FiscalYear(
                empresa_id=empresa_id,
                year=anio,
                date_start=date(anio, 1, 1),
                date_end=date(anio, 12, 31),
                is_closed=False,
            )
        )
    await db.flush()
    cliente = await tercero(
        db, empresa_id, f"Cliente {empresa_id}", f"A{empresa_id:07d}", es_cliente=True
    )
    proveedor = await tercero(
        db,
        empresa_id,
        f"Proveedor {empresa_id}",
        f"B{empresa_id:07d}",
        es_cliente=False,
        es_proveedor=True,
    )
    serie = SerieFactura(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        codigo=f"F{empresa_id}",
        nombre="Serie principal",
        prefijo=f"F{empresa_id}-",
        siguiente_numero=3,
    )
    db.add(serie)
    await db.flush()
    ventas = await factura(
        db,
        empresa_id=empresa_id,
        tercero_id=cliente.id,
        serie_id=serie.id,
        ejercicio=ejercicios[0],
        numero=1,
        fecha=date(ejercicios[0], 3, 15),
        tipo=FacturaTipo.VENTA,
        base=Decimal("1000.0000"),
        iva=Decimal("210.0000"),
        total=Decimal("1210.0000"),
    )
    compras = None
    if con_compras:
        compras = await factura(
            db,
            empresa_id=empresa_id,
            tercero_id=proveedor.id,
            serie_id=serie.id,
            ejercicio=ejercicios[-1],
            numero=2,
            fecha=date(ejercicios[-1], 5, 20),
            tipo=FacturaTipo.COMPRA,
            base=Decimal("500.0000"),
            iva=Decimal("105.0000"),
            total=Decimal("605.0000"),
        )
    for indice, anio in enumerate(ejercicios):
        await asiento(
            db,
            empresa_id=empresa_id,
            fecha=date(anio, 2, 10 + indice),
            lineas=[
                (CUENTAS["cliente"], Decimal("1210.0000"), Decimal("0.0000")),
                (CUENTAS["ventas"], Decimal("0.0000"), Decimal("1000.0000")),
                (CUENTAS["iva_repercutido"], Decimal("0.0000"), Decimal("210.0000")),
            ],
            concepto=f"Venta {anio}",
        )
    db.add(
        Vencimiento(
            id=uuid.uuid4(),
            empresa_id=empresa_id,
            tercero_id=cliente.id,
            factura_id=ventas.id,
            recibo_num=f"REC-{empresa_id}",
            iban="ES9121000418450200051332",
            ejercicio=ejercicios[0],
            tipo=TipoVencimiento.cobro,
            fecha_vencimiento=date(ejercicios[0], 4, 30),
            importe=Decimal("1210.0000"),
            estado=EstadoVencimiento.pendiente,
        )
    )
    if con_sii:
        db.add(
            ConfigSii(
                id=uuid.uuid4(),
                empresa_id=empresa_id,
                obligado_sii=True,
                sin_anexo=False,
                clave_regimen="01",
                fecha_alta=date(ejercicios[0], 1, 1),
            )
        )
    await db.flush()
    return {
        "cliente_id": cliente.id,
        "proveedor_id": proveedor.id,
        "serie_id": serie.id,
        "factura_venta_id": ventas.id,
        "factura_compra_id": compras.id if compras else None,
    }


def bloque_de_prueba(
    nombre: str, fichero: str, filas: list[dict], **kwargs: Any
) -> BloqueRecopilado:
    """`BloqueRecopilado` sintetico para probar el ZIP y el manifiesto sin BD."""
    return BloqueRecopilado(
        bloque=Bloque(
            nombre=nombre,
            fichero=fichero,
            descripcion=kwargs.pop("descripcion", "Bloque de prueba"),
            tablas=(),
            filtra_ejercicio=kwargs.pop("filtra_ejercicio", True),
        ),
        registros=filas,
        conteo_registros=len(filas),
        ejercicio_min=kwargs.pop("ejercicio_min", 2025),
        ejercicio_max=kwargs.pop("ejercicio_max", 2026),
        fecha_min=kwargs.pop("fecha_min", date(2025, 1, 1)),
        fecha_max=kwargs.pop("fecha_max", date(2026, 12, 31)),
        **kwargs,
    )