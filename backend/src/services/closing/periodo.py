"""Cierre de periodos intermedios (SPEC-028 T019, US1/FR-001).

`cerrar_periodo_intermedio` es atomico (boundary ACID de `get_db`): valida el
rango derivado del calendario, calcula el balance de comprobacion del periodo
(research D1), persiste el snapshot inmutable y el `PeriodoCerrado` en estado
`cerrado`, y audita. **No crea ni modifica asientos del diario**: la
contabilizacion de ese rango queda bloqueada por `validar_periodo_abierto`
(usada por el motor de SPEC-002) y por el trigger
`chk_journal_entry_fecha_abierta`.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.closing.balanza_periodo import BalanzaPeriodoLinea
from models.closing.periodo_cerrado import (
    EstadoPeriodo,
    PeriodoCerrado,
    TipoPeriodo,
)
from services.audit.writer import audit_escribir
from services.closing.balanza import (
    calcular_balanza_periodo,
    leer_balanza,
    persistir_balanza,
)
from services.closing.errores import error
from services.closing.reglas_cierre import (
    meses_del_periodo,
    rango_periodo,
    solapan,
    tipo_periodo_de,
    validar_ejercicio_abierto,
)


async def _periodo_existente(
    db: AsyncSession, empresa_id: int, ejercicio: int, tipo: TipoPeriodo, periodo: int
) -> PeriodoCerrado | None:
    return await db.scalar(
        select(PeriodoCerrado).where(
            PeriodoCerrado.empresa_id == empresa_id,
            PeriodoCerrado.ejercicio == ejercicio,
            PeriodoCerrado.tipo == tipo,
            PeriodoCerrado.periodo == periodo,
        )
    )


async def _periodo_que_cubre(
    db: AsyncSession,
    empresa_id: int,
    ejercicio: int,
    fecha_ini: date,
    fecha_fin: date,
    excluir: uuid.UUID | None = None,
) -> PeriodoCerrado | None:
    """Periodo ya cerrado (mes o trimestre) cuyo rango solape con el pedido."""
    candidatos = (
        await db.scalars(
            select(PeriodoCerrado)
            .where(
                PeriodoCerrado.empresa_id == empresa_id,
                PeriodoCerrado.ejercicio == ejercicio,
                PeriodoCerrado.estado != EstadoPeriodo.reabierto_ajuste,
            )
            .order_by(PeriodoCerrado.fecha_ini)
        )
    ).all()
    for candidato in candidatos:
        if excluir is not None and candidato.id == excluir:
            continue
        if solapan(fecha_ini, fecha_fin, candidato.fecha_ini, candidato.fecha_fin):
            return candidato
    return None


async def cerrar_periodo_intermedio(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    tipo: str | TipoPeriodo,
    periodo: int,
    actor: str | None = None,
    ip: str | None = None,
) -> dict[str, Any]:
    """Cierra un mes o trimestre: snapshot de balanza + bloqueo del periodo."""
    tipo_enum = tipo_periodo_de(tipo)
    fecha_ini, fecha_fin = rango_periodo(ejercicio, tipo_enum, periodo)
    await validar_ejercicio_abierto(db, empresa_id, ejercicio)

    existente = await _periodo_existente(db, empresa_id, ejercicio, tipo_enum, periodo)
    if existente is not None:
        raise error(
            "periodo_ya_cerrado",
            f"El periodo {tipo_enum.value} {periodo} de {ejercicio} ya esta cerrado",
            409,
        )
    cubre = await _periodo_que_cubre(db, empresa_id, ejercicio, fecha_ini, fecha_fin)
    if cubre is not None:
        raise error(
            "periodo_cubierto",
            (
                f"El rango {fecha_ini.isoformat()}..{fecha_fin.isoformat()} ya esta "
                f"cubierto por el periodo {cubre.tipo.value} {cubre.periodo} cerrado"
            ),
            409,
        )

    periodo_id = uuid.uuid4()
    cabecera, lineas = await calcular_balanza_periodo(
        db,
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        tipo=tipo_enum.value,
        periodo=periodo,
        fecha_ini=fecha_ini,
        fecha_fin=fecha_fin,
        periodo_id=periodo_id,
        actor=actor,
    )

    # El periodo se inserta primero porque `balanza_periodo.periodo_id` lo
    # referencia por FK compuesta; ambas filas quedan en la misma transaccion
    # ACID, asi que el cierre sigue siendo atomico.
    fila = PeriodoCerrado(
        id=periodo_id,
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        tipo=tipo_enum,
        periodo=periodo,
        fecha_ini=fecha_ini,
        fecha_fin=fecha_fin,
        estado=EstadoPeriodo.cerrado,
        cerrado_por=actor,
        cerrado_at=datetime.now(timezone.utc),
        n_reaperturas=0,
    )
    db.add(fila)
    await db.flush()

    await persistir_balanza(db, cabecera, lineas)
    fila.balanza_id = cabecera.id
    await db.flush()

    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="CERRAR_PERIODO",
        entity="periodo_cerrado",
        entity_id=str(fila.id),
        ip=ip,
        payload={
            "ejercicio": ejercicio,
            "tipo": tipo_enum.value,
            "periodo": periodo,
            "fecha_ini": fecha_ini.isoformat(),
            "fecha_fin": fecha_fin.isoformat(),
            "total_debe": f"{cabecera.total_debe:0.4f}",
            "total_haber": f"{cabecera.total_haber:0.4f}",
            "n_lineas": cabecera.n_lineas,
            "sha256": cabecera.sha256,
        },
    )
    await db.flush()
    return {
        "periodo": fila,
        "balanza": cabecera,
        "lineas": lineas,
    }


async def listar_periodos(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int | None = None,
    tipo: str | None = None,
    estado: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """Periodos cerrados de la empresa, con filtros y paginacion (tenant-scoped)."""
    filtros: list[Any] = [PeriodoCerrado.empresa_id == empresa_id]
    if ejercicio is not None:
        filtros.append(PeriodoCerrado.ejercicio == ejercicio)
    if tipo:
        filtros.append(PeriodoCerrado.tipo == TipoPeriodo(str(tipo).upper()))
    if estado:
        filtros.append(PeriodoCerrado.estado == EstadoPeriodo(str(estado).lower()))

    total = await db.scalar(
        select(func.count()).select_from(PeriodoCerrado).where(*filtros)
    )
    filas = (
        await db.scalars(
            select(PeriodoCerrado)
            .where(*filtros)
            .order_by(PeriodoCerrado.ejercicio.desc(), PeriodoCerrado.tipo, PeriodoCerrado.periodo)
            .offset(max(page - 1, 0) * page_size)
            .limit(page_size)
        )
    ).all()
    return {"items": list(filas), "total": int(total or 0), "page": page}


async def calendario_periodos(
    db: AsyncSession, *, empresa_id: int, ejercicio: int, tipo: str | TipoPeriodo
) -> list[dict[str, Any]]:
    """Meses o trimestres del ejercicio con su estado y rango.

    Un periodo sin fila `PeriodoCerrado` esta `abierto` (research D2: no hay
    tabla de calendario persistida). Solo se materializan los periodos que el
    calendario define, de modo que la lista es siempre completa.
    """
    tipo_enum = tipo if isinstance(tipo, TipoPeriodo) else TipoPeriodo(str(tipo).upper())
    total = 12 if tipo_enum is TipoPeriodo.MES else 4
    cerrados = {
        fila.periodo: fila
        for fila in (
            await db.scalars(
                select(PeriodoCerrado).where(
                    PeriodoCerrado.empresa_id == empresa_id,
                    PeriodoCerrado.ejercicio == ejercicio,
                    PeriodoCerrado.tipo == tipo_enum,
                )
            )
        ).all()
    }
    items: list[dict[str, Any]] = []
    for numero in range(1, total + 1):
        fecha_ini, fecha_fin = rango_periodo(ejercicio, tipo_enum, numero)
        fila = cerrados.get(numero)
        items.append(
            {
                "periodo_id": fila.id if fila is not None else None,
                "ejercicio": ejercicio,
                "tipo": tipo_enum.value,
                "periodo": numero,
                "fecha_ini": fecha_ini,
                "fecha_fin": fecha_fin,
                "estado": fila.estado.value if fila is not None else EstadoPeriodo.abierto.value,
                "n_reaperturas": fila.n_reaperturas if fila is not None else 0,
                "balanza_id": fila.balanza_id if fila is not None else None,
                "cerrado_at": fila.cerrado_at if fila is not None else None,
                "cerrado_por": fila.cerrado_por if fila is not None else None,
            }
        )
    return items


async def obtener_balanza_periodo(
    db: AsyncSession, *, empresa_id: int, periodo_id: uuid.UUID
) -> tuple[Any, list[BalanzaPeriodoLinea]]:
    """Cabecera y lineas del snapshot; 404 si el periodo no existe en la empresa."""
    fila = await db.scalar(
        select(PeriodoCerrado).where(
            PeriodoCerrado.empresa_id == empresa_id, PeriodoCerrado.id == periodo_id
        )
    )
    if fila is None:
        raise error(
            "periodo_no_encontrado",
            "Periodo de cierre inexistente en la empresa activa",
            404,
        )
    snapshot = await leer_balanza(db, empresa_id, periodo_id)
    if snapshot is None:
        raise error(
            "balanza_no_encontrada",
            "El periodo no tiene balance de comprobacion registrado",
            404,
        )
    return snapshot


async def periodos_pendientes(
    db: AsyncSession, *, empresa_id: int, ejercicio: int
) -> list[dict[str, Any]]:
    """Meses del ejercicio que no estan cerrados (US2 los exige antes del cierre)."""
    items = await calendario_periodos(
        db, empresa_id=empresa_id, ejercicio=ejercicio, tipo=TipoPeriodo.MES
    )
    return [item for item in items if item["estado"] == EstadoPeriodo.abierto.value]


async def meses_cubiertos(
    db: AsyncSession, *, empresa_id: int, ejercicio: int
) -> set[int]:
    """Meses con algun periodo bloqueante (mes cerrado o trimestre cerrado).

    Un periodo en `reabierto_ajuste` deja de cubrir su mes: el asiento
    rectificativo ya puede asentarse, asi que el mes sigue pendiente de cerrar
    de nuevo (y por tanto bloquea el cierre anual).
    """
    filas = (
        await db.execute(
            select(PeriodoCerrado.tipo, PeriodoCerrado.periodo, PeriodoCerrado.estado).where(
                PeriodoCerrado.empresa_id == empresa_id,
                PeriodoCerrado.ejercicio == ejercicio,
            )
        )
    ).all()
    cubiertos: set[int] = set()
    for tipo, periodo, estado in filas:
        if EstadoPeriodo(estado) == EstadoPeriodo.reabierto_ajuste:
            continue
        cubiertos.update(meses_del_periodo(tipo, periodo))
    return cubiertos


__all__ = [
    "calendario_periodos",
    "cerrar_periodo_intermedio",
    "listar_periodos",
    "meses_cubiertos",
    "obtener_balanza_periodo",
    "periodos_pendientes",
]
