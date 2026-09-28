"""Acumulación tenant-scoped de retenciones IRPF desde facturas."""

from __future__ import annotations

import calendar
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.ar.tercero import Tercero
from models.fiscal.liquidacion_retenciones import (
    EstadoLiquidacionRetenciones,
    LiquidacionRetenciones,
)
from models.fiscal.retencion import RetencionPeriodo, TipoRetencion
from models.invoice.factura import Factura, FacturaEstado, FacturaTipo
from models.invoice.factura_linea import FacturaLinea
from services.audit import registrar_auditoria
from services.fiscal.errores import error

Q4 = Decimal("0.0001")
Q2 = Decimal("0.01")
CERO = Decimal("0.0000")
AÑO_MIN = 2000
AÑO_MAX = 2100


def _q4(valor: Decimal | str | int) -> Decimal:
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise error("importe_invalido", "El importe no es decimal") from exc
    if not numero.is_finite():
        raise error("importe_invalido", "El importe no es finito")
    return numero.quantize(Q4, rounding=ROUND_HALF_EVEN)


def _q2(valor: Decimal | str | int) -> Decimal:
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise error("tipo_irpf_invalido", "El tipo de IRPF no es decimal") from exc
    if not numero.is_finite():
        raise error("tipo_irpf_invalido", "El tipo de IRPF no es finito")
    return numero.quantize(Q2, rounding=ROUND_HALF_EVEN)


def d4(valor: Decimal | str | int) -> str:
    return f"{_q4(valor):0.4f}"


def d2(valor: Decimal | str | int) -> str:
    return f"{_q2(valor):0.2f}"


def _periodo(ejercicio: int, trimestre: int) -> tuple[date, date, str]:
    if not AÑO_MIN <= ejercicio <= AÑO_MAX:
        raise error("ejercicio_invalido", "El ejercicio no es válido")
    if trimestre not in (1, 2, 3, 4):
        raise error("trimestre_invalido", "El trimestre debe estar entre 1 y 4")
    mes_inicio = 3 * (trimestre - 1) + 1
    mes_fin = mes_inicio + 2
    inicio = date(ejercicio, mes_inicio, 1)
    fin = date(ejercicio, mes_fin, calendar.monthrange(ejercicio, mes_fin)[1])
    return inicio, fin, f"{ejercicio}-Q{trimestre}"


def _categoria(linea: FacturaLinea, tasa: Decimal) -> TipoRetencion:
    valor = getattr(linea, "tipo_retencion", None)
    if isinstance(valor, TipoRetencion):
        valor = valor.value
    if valor in (None, ""):
        valor = None
    if valor == TipoRetencion.IRPF_OTROS.value and tasa in (
        Decimal("19.00"),
        Decimal("15.00"),
        Decimal("7.00"),
        Decimal("1.00"),
    ):
        valor = None
    if valor is not None:
        try:
            return TipoRetencion(str(valor))
        except (TypeError, ValueError) as exc:
            raise error(
                "tipo_retencion_invalido", "La categoría de retención no es válida"
            ) from exc
    if tasa == Decimal("19.00"):
        return TipoRetencion.IRPF_ARRENDAMIENTOS
    if tasa == Decimal("15.00"):
        return TipoRetencion.IRPF_PROFESIONALES
    if tasa in (Decimal("7.00"), Decimal("1.00")):
        return TipoRetencion.IRPF_OBRAS
    return TipoRetencion.IRPF_OTROS


@dataclass
class _Grupo:
    tercero_id: uuid.UUID
    tipo_retencion: TipoRetencion
    tasa: Decimal
    nombre: str
    nif: str
    base: Decimal = CERO
    retencion: Decimal = CERO
    facturas: list[dict[str, object]] = field(default_factory=list)
    direccion_inmueble: str | None = None


def _base_linea(linea: FacturaLinea) -> Decimal:
    base = _q4(linea.base_irpf or CERO)
    if base <= 0:
        base = _q4(linea.base or CERO)
    if base <= 0:
        raise error("base_irpf_invalida", "La base de la retención debe ser positiva")
    return base


def _tasa_linea(linea: FacturaLinea, base: Decimal, retencion: Decimal) -> Decimal:
    tasa = _q2(linea.tipo_irpf or CERO)
    if tasa <= 0:
        tasa = _q2(retencion * Decimal(100) / base)
    if tasa <= 0 or tasa > Decimal(100):
        raise error("tipo_irpf_invalido", "El tipo de IRPF debe estar entre 0 y 100")
    return tasa


async def _filas_fuente(
    db: AsyncSession, *, empresa_id: int, inicio: date, fin: date
) -> list[tuple[Factura, FacturaLinea, Tercero]]:
    condiciones = [
        Factura.empresa_id == empresa_id,
        Factura.fecha >= inicio,
        Factura.fecha <= fin,
        Factura.asiento_id.is_not(None),
        FacturaLinea.empresa_id == empresa_id,
        FacturaLinea.cuota_irpf > 0,
    ]
    rectificativa = Factura.__table__.alias("factura_rectificativa")
    existe_rectificativa = exists(
        select(rectificativa.c.id).where(
            rectificativa.c.empresa_id == Factura.empresa_id,
            rectificativa.c.factura_original_id == Factura.id,
            rectificativa.c.tipo == FacturaTipo.RECTIFICATIVA,
        )
    )
    condiciones.append(
        or_(
            Factura.estado == FacturaEstado.emitida,
            and_(
                Factura.estado == FacturaEstado.anulada,
                existe_rectificativa,
            ),
        )
    )
    filas = (
        await db.execute(
            select(Factura, FacturaLinea, Tercero)
            .join(
                FacturaLinea,
                and_(
                    FacturaLinea.empresa_id == Factura.empresa_id,
                    FacturaLinea.factura_id == Factura.id,
                ),
            )
            .join(
                Tercero,
                and_(
                    Tercero.empresa_id == Factura.empresa_id,
                    Tercero.id == Factura.tercero_id,
                ),
            )
            .where(*condiciones)
            .order_by(Factura.fecha, Factura.id, FacturaLinea.line_no, FacturaLinea.id)
        )
    ).all()
    return [(row[0], row[1], row[2]) for row in filas]


def _snapshot(
    factura: Factura,
    linea: FacturaLinea,
    categoria: TipoRetencion,
    *,
    signo: int,
    base: Decimal,
    retencion: Decimal,
    tasa: Decimal,
) -> dict[str, object]:
    direccion = linea.direccion_inmueble
    return {
        "factura_id": str(factura.id),
        "numero": factura.numero,
        "fecha": factura.fecha.isoformat(),
        "tipo_factura": factura.tipo.value,
        "signo": signo,
        "tipo_retencion": categoria.value,
        "tipo_irpf": d2(tasa),
        "importe_base": d4(signo * base),
        "base_imponible": d4(signo * base),
        "retencion": d4(signo * retencion),
        "retencion_practicada": d4(signo * retencion),
        "direccion_inmueble": direccion,
    }


async def _existe_liquidacion(
    db: AsyncSession, *, empresa_id: int, ejercicio: int, trimestre: int
) -> LiquidacionRetenciones | None:
    return await db.scalar(
        select(LiquidacionRetenciones)
        .where(
            LiquidacionRetenciones.empresa_id == empresa_id,
            LiquidacionRetenciones.ejercicio == ejercicio,
            LiquidacionRetenciones.trimestre == trimestre,
        )
        .with_for_update()
    )


async def acumular_retenciones(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    trimestre: int,
    actor: str | None = None,
    ip: str | None = None,
    notas: str | None = None,
) -> LiquidacionRetenciones:
    """Acumula el trimestre natural y persiste sus grupos por perceptor."""
    inicio, fin, periodo = _periodo(ejercicio, trimestre)
    if await _existe_liquidacion(
        db, empresa_id=empresa_id, ejercicio=ejercicio, trimestre=trimestre
    ) is not None:
        raise error(
            "liquidacion_ya_existente",
            "Ya existe una liquidación para el ejercicio y trimestre",
        )

    grupos: OrderedDict[tuple[uuid.UUID, TipoRetencion, Decimal], _Grupo] = OrderedDict()
    for factura, linea, tercero in await _filas_fuente(
        db, empresa_id=empresa_id, inicio=inicio, fin=fin
    ):
        base = _base_linea(linea)
        retencion = _q4(linea.cuota_irpf)
        tasa = _tasa_linea(linea, base, retencion)
        categoria = _categoria(linea, tasa)
        signo = -1 if factura.tipo == FacturaTipo.RECTIFICATIVA else 1
        clave = (factura.tercero_id, categoria, tasa)
        grupo = grupos.get(clave)
        if grupo is None:
            grupo = _Grupo(
                tercero_id=factura.tercero_id,
                tipo_retencion=categoria,
                tasa=tasa,
                nombre=tercero.nombre[:100],
                nif=(tercero.nif or "")[:9],
            )
            grupos[clave] = grupo
        grupo.base = _q4(grupo.base + signo * base)
        grupo.retencion = _q4(grupo.retencion + signo * retencion)
        if grupo.direccion_inmueble is None and linea.direccion_inmueble:
            grupo.direccion_inmueble = linea.direccion_inmueble[:200]
        grupo.facturas.append(
            _snapshot(
                factura,
                linea,
                categoria,
                signo=signo,
                base=base,
                retencion=retencion,
                tasa=tasa,
            )
        )

    grupos_validos = [
        grupo
        for grupo in grupos.values()
        if grupo.base > 0 and grupo.retencion > 0
    ]
    total_base = _q4(sum((grupo.base for grupo in grupos_validos), CERO))
    total_retenciones = _q4(sum((grupo.retencion for grupo in grupos_validos), CERO))
    n_perceptores = len({grupo.tercero_id for grupo in grupos_validos})
    liquidacion = LiquidacionRetenciones(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        trimestre=trimestre,
        periodo=periodo,
        total_base_retenciones=total_base,
        total_retenciones=total_retenciones,
        n_perceptores=n_perceptores,
        estado=EstadoLiquidacionRetenciones.pendiente,
        notas=notas,
        created_by=actor,
    )
    db.add(liquidacion)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise error(
            "liquidacion_ya_existente",
            "Ya existe una liquidación para el ejercicio y trimestre",
        ) from exc

    for grupo in grupos_validos:
        db.add(
            RetencionPeriodo(
                id=uuid.uuid4(),
                empresa_id=empresa_id,
                liquidacion_retenciones_id=liquidacion.id,
                tercero_id=grupo.tercero_id,
                nif=grupo.nif,
                nombre=grupo.nombre,
                tipo_retencion=grupo.tipo_retencion,
                base_imponible=grupo.base,
                tipo_porcentaje=grupo.tasa,
                retencion_practicada=grupo.retencion,
                facturas=grupo.facturas,
                notas=grupo.direccion_inmueble,
                created_by=actor,
            )
        )
    await db.flush()
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        usuario=actor or "system",
        operacion="ACUMULAR_RETENCIONES",
        entidad="liquidacion_retenciones",
        entidad_id=liquidacion.id,
        payload={
            "ejercicio": ejercicio,
            "trimestre": trimestre,
            "periodo": periodo,
            "total_base_retenciones": d4(total_base),
            "total_retenciones": d4(total_retenciones),
            "n_perceptores": n_perceptores,
        },
        ip=ip,
    )
    return liquidacion


async def obtener_liquidacion(
    db: AsyncSession, *, empresa_id: int, liquidacion_id: uuid.UUID
) -> LiquidacionRetenciones | None:
    """Devuelve la liquidación solo si pertenece a la empresa activa."""
    return await db.scalar(
        select(LiquidacionRetenciones).where(
            LiquidacionRetenciones.empresa_id == empresa_id,
            LiquidacionRetenciones.id == liquidacion_id,
        )
    )


async def listar_retenciones_periodo(
    db: AsyncSession, *, empresa_id: int, liquidacion_id: uuid.UUID
) -> list[RetencionPeriodo]:
    """Lista los grupos de una liquidación dentro de la empresa activa."""
    return list(
        (
            await db.scalars(
                select(RetencionPeriodo)
                .where(
                    RetencionPeriodo.empresa_id == empresa_id,
                    RetencionPeriodo.liquidacion_retenciones_id == liquidacion_id,
                )
                .order_by(
                    RetencionPeriodo.nombre,
                    RetencionPeriodo.tipo_retencion,
                    RetencionPeriodo.tipo_porcentaje,
                    RetencionPeriodo.id,
                )
            )
        ).all()
    )


async def listar_liquidaciones(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int | None = None,
    trimestre: int | None = None,
    estado: EstadoLiquidacionRetenciones | str | None = None,
    pagina: int = 1,
    tamano: int = 50,
) -> tuple[list[LiquidacionRetenciones], int]:
    """Lista liquidaciones filtradas por empresa, periodo y estado."""
    if pagina < 1 or tamano < 1 or tamano > 200:
        raise error("paginacion_invalida", "La paginación no es válida")
    filtros = [LiquidacionRetenciones.empresa_id == empresa_id]
    if ejercicio is not None:
        filtros.append(LiquidacionRetenciones.ejercicio == ejercicio)
    if trimestre is not None:
        filtros.append(LiquidacionRetenciones.trimestre == trimestre)
    if estado is not None:
        try:
            estado_normalizado = (
                estado if isinstance(estado, EstadoLiquidacionRetenciones) else EstadoLiquidacionRetenciones(estado)
            )
        except ValueError as exc:
            raise error("estado_invalido", "El estado de liquidación no es válido") from exc
        filtros.append(LiquidacionRetenciones.estado == estado_normalizado)
    total = int(
        await db.scalar(
            select(func.count()).select_from(LiquidacionRetenciones).where(*filtros)
        )
        or 0
    )
    filas = (
        await db.scalars(
            select(LiquidacionRetenciones)
            .where(*filtros)
            .order_by(
                LiquidacionRetenciones.ejercicio.desc(),
                LiquidacionRetenciones.trimestre.desc(),
                LiquidacionRetenciones.created_at.desc(),
            )
            .offset((pagina - 1) * tamano)
            .limit(tamano)
        )
    ).all()
    return list(filas), total


def payload_liquidacion(liquidacion: LiquidacionRetenciones) -> dict[str, Any]:
    return {
        "id": str(liquidacion.id),
        "ejercicio": liquidacion.ejercicio,
        "trimestre": liquidacion.trimestre,
        "periodo": liquidacion.periodo,
        "total_base_retenciones": d4(liquidacion.total_base_retenciones),
        "total_retenciones": d4(liquidacion.total_retenciones),
        "n_perceptores": liquidacion.n_perceptores,
        "estado": liquidacion.estado.value,
        "fecha_liquidacion": (
            liquidacion.fecha_liquidacion.isoformat()
            if liquidacion.fecha_liquidacion is not None
            else None
        ),
        "asiento_id": str(liquidacion.asiento_id) if liquidacion.asiento_id else None,
        "modelo_111_id": (
            str(liquidacion.modelo_111_id) if liquidacion.modelo_111_id else None
        ),
        "modelo_115_id": (
            str(liquidacion.modelo_115_id) if liquidacion.modelo_115_id else None
        ),
        "notas": liquidacion.notas,
    }


def payload_retencion(retencion: RetencionPeriodo) -> dict[str, Any]:
    return {
        "id": str(retencion.id),
        "liquidacion_retenciones_id": str(retencion.liquidacion_retenciones_id),
        "tercero_id": str(retencion.tercero_id),
        "nif": retencion.nif or "",
        "nombre": retencion.nombre,
        "tipo_retencion": retencion.tipo_retencion.value,
        "base_imponible": d4(retencion.base_imponible),
        "tipo_porcentaje": d2(retencion.tipo_porcentaje),
        "retencion_practicada": d4(retencion.retencion_practicada),
        "facturas": list(retencion.facturas or []),
        "notas": retencion.notas,
    }


async def obtener_detalle_liquidacion(
    db: AsyncSession, *, empresa_id: int, liquidacion_id: uuid.UUID
) -> dict[str, Any] | None:
    """Compone la liquidación y sus retenciones sin cruzar empresas."""
    liquidacion = await obtener_liquidacion(
        db, empresa_id=empresa_id, liquidacion_id=liquidacion_id
    )
    if liquidacion is None:
        return None
    detalle = payload_liquidacion(liquidacion)
    detalle["retenciones"] = [
        payload_retencion(retencion)
        for retencion in await listar_retenciones_periodo(
            db, empresa_id=empresa_id, liquidacion_id=liquidacion_id
        )
    ]
    return detalle


__all__ = [
    "acumular_retenciones",
    "d2",
    "d4",
    "listar_liquidaciones",
    "listar_retenciones_periodo",
    "obtener_detalle_liquidacion",
    "obtener_liquidacion",
    "payload_liquidacion",
    "payload_retencion",
]
