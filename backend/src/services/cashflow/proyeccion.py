"""Proyeccion de tesoreria (SPEC-027 US1, T015/T016).

`recuperar_movimientos_proyectables` lee los vencimientos pendientes
(SPEC-011/020) y decide, uno a uno, si entran en la proyeccion (FR-006) o si
quedan fuera con un motivo trazable. `generar_prevision` materializa la
cabecera, los movimientos, los buckets y las alertas en una sola transaccion
(boundary ACID del proyecto: `get_db` + `flush()`).

research.md D2: `saldo_k = saldo_inicial + S(movimientos hasta k)`, agregado por
la granularidad elegida. Constitucion IV: `numero_prevision` correlativo por
empresa asignado bajo `SELECT ... FOR UPDATE`.
"""

from __future__ import annotations

import calendar
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.treasury.alerta_liquidez import AlertaLiquidez
from models.treasury.movimiento_prevision import (
    FrecuenciaMovimiento,
    MovimientoPrevision,
    OrigenMovimientoPrevision,
    TipoMovimientoPrevision,
)
from models.treasury.prevision import (
    EstadoPrevision,
    GranularidadPrevision,
    PrevisionTesoreria,
)
from services.audit import registrar_auditoria
from services.cashflow.errores import error
from services.cashflow.saldos import saldo_tesoreria_inicial
from services.cashflow.utils import (
    Bucket,
    agrupar_en_buckets,
    c4,
    enumerar_buckets,
    fmt,
)

__all__ = [
    "DIAS_MAXIMOS_PREVISION",
    "MOTIVO_ANULADO",
    "MOTIVO_COBRADO",
    "MOTIVO_SIN_FECHA",
    "MOTIVO_VENCIDO",
    "aplicar_movimiento_manual",
    "buckets_desde_movimientos",
    "detalle_prevision",
    "generar_prevision",
    "listar_previsiones",
    "movimientos_de_prevision",
    "obtener_prevision",
    "proximo_numero_prevision",
    "recuperar_movimientos_proyectables",
    "regenerar_prevision",
]

#: Tope defensivo del rango proyectable (~5 anos) para no generar una cantidad
#: absurda de buckets por una peticion mal formada.
DIAS_MAXIMOS_PREVISION = 1830

#: Importe minimo persistible: la columna exige `importe > 0` y un excluded con
#: saldo residual cero (cobro ya liquidado) se registra con el minimo.
IMPORTE_MINIMO = Decimal("0.0001")

MOTIVO_ANULADO = "anulado"
MOTIVO_COBRADO = "cobrado"
MOTIVO_SIN_FECHA = "sin_fecha"
MOTIVO_VENCIDO = "vencido"

#: Estados de `Vencimiento` que ya no generan flujo futuro (FR-006).
ESTADOS_LIQUIDADOS: frozenset[EstadoVencimiento] = frozenset(
    {
        EstadoVencimiento.cobrado,
        EstadoVencimiento.remesado,
        EstadoVencimiento.devuelto,
        EstadoVencimiento.anulado,
    }
)
MOTIVO_POR_ESTADO: dict[EstadoVencimiento, str] = {
    EstadoVencimiento.cobrado: MOTIVO_COBRADO,
    EstadoVencimiento.remesado: MOTIVO_COBRADO,
    EstadoVencimiento.devuelto: MOTIVO_COBRADO,
    EstadoVencimiento.anulado: MOTIVO_ANULADO,
}

ORIGEN_VENCIMIENTO = "vencimiento"


# --- Correlatividad (constitucion IV) ---------------------------------------


async def proximo_numero_prevision(db: AsyncSession, empresa_id: int) -> int:
    """Siguiente `numero_prevision` sin saltos, con bloqueo de fila.

    El `SELECT ... FOR UPDATE` sobre el MAX por empresa serializa a los emisores
    concurrentes. Sobre la tabla vacia devuelve 1.
    """
    ultimo = await db.scalar(
        select(func.max(PrevisionTesoreria.numero_prevision))
        .where(PrevisionTesoreria.empresa_id == empresa_id)
        .with_for_update()
    )
    return int(ultimo or 0) + 1


# --- Validacion de entradas --------------------------------------------------


def _granularidad(valor: str | None) -> GranularidadPrevision:
    try:
        return GranularidadPrevision(valor or GranularidadPrevision.dia.value)
    except ValueError as exc:
        raise error(
            "granularidad_invalida", f"Granularidad no soportada: {valor!r}", 422
        ) from exc


def _frecuencia(valor: str | None) -> FrecuenciaMovimiento:
    try:
        return FrecuenciaMovimiento(valor or FrecuenciaMovimiento.unico.value)
    except ValueError as exc:
        raise error(
            "frecuencia_invalida", f"Frecuencia no soportada: {valor!r}", 422
        ) from exc


def _validar_tipo(valor: Any) -> TipoMovimientoPrevision:
    try:
        return TipoMovimientoPrevision(str(valor))
    except ValueError as exc:
        raise error("tipo_invalido", f"Tipo no soportado: {valor!r}", 422) from exc


def _importe(valor: Any) -> Decimal:
    """Importe decimal exacto `> 0`; rechaza `float` (constitucion)."""
    if isinstance(valor, float):
        raise error(
            "importe_invalido",
            "El importe debe enviarse como cadena decimal, no como numero flotante",
            422,
        )
    try:
        importe = c4(Decimal(str(valor)))
    except ArithmeticError as exc:
        raise error("importe_invalido", f"Importe no decimal: {valor!r}", 422) from exc
    if importe <= 0:
        raise error("importe_invalido", "El importe debe ser mayor que cero", 422)
    return importe


def _fecha_iso(valor: Any) -> date:
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor))
    except ValueError as exc:
        raise error("fecha_invalida", f"Fecha no valida: {valor!r}", 422) from exc


def _validar_rango(desde_fecha: date, hasta_fecha: date) -> None:
    if hasta_fecha < desde_fecha:
        raise error(
            "rango_invalido",
            "La fecha de fin no puede ser anterior a la de inicio",
            422,
        )
    if (hasta_fecha - desde_fecha).days > DIAS_MAXIMOS_PREVISION:
        raise error(
            "rango_demasiado_amplo",
            f"El rango no puede superar {DIAS_MAXIMOS_PREVISION} dias",
            422,
        )


# --- US1 / T015: recuperacion de movimientos proyectables -------------------


async def recuperar_movimientos_proyectables(
    db: AsyncSession,
    *,
    empresa_id: int,
    desde_fecha: date,
    hasta_fecha: date,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Vencimientos de la empresa, separados en proyectados y excluidos (T015).

    Devuelve `(proyectados, excluidos)`; cada dict lleva `origen`, `tipo`,
    `importe` y `fecha_prevista` (o `motivo` en los excluidos). Los excluidos se
    reportan con su motivo para que el usuario sepa por que un cobro esperado
    no aparece en la proyeccion.
    """
    vencimientos = (
        await db.scalars(
            select(Vencimiento)
            .where(
                Vencimiento.empresa_id == empresa_id,
                Vencimiento.fecha_vencimiento <= hasta_fecha,
            )
            .order_by(Vencimiento.fecha_vencimiento, Vencimiento.recibo_num)
        )
    ).all()

    proyectados: list[dict[str, Any]] = []
    excluidos: list[dict[str, Any]] = []
    for vencimiento in vencimientos:
        base: dict[str, Any] = {
            "origen": ORIGEN_VENCIMIENTO,
            "vencimiento_id": vencimiento.id,
            "numero_recibo": vencimiento.recibo_num,
            "tipo": vencimiento.tipo.value,
            "importe": c4(vencimiento.saldo_pendiente),
            "fecha_vencimiento": vencimiento.fecha_vencimiento,
            "concepto": f"Vencimiento {vencimiento.recibo_num}",
            "frecuencia": FrecuenciaMovimiento.unico.value,
        }
        if vencimiento.estado in ESTADOS_LIQUIDADOS:
            base["motivo"] = MOTIVO_POR_ESTADO[vencimiento.estado]
            excluidos.append(base)
        elif vencimiento.saldo_pendiente <= 0:
            base["motivo"] = MOTIVO_COBRADO
            excluidos.append(base)
        elif vencimiento.fecha_vencimiento < desde_fecha:
            # FR-006: los vencidos quedan fuera de la proyeccion futura.
            base["motivo"] = MOTIVO_VENCIDO
            excluidos.append(base)
        else:
            base["fecha_prevista"] = vencimiento.fecha_vencimiento
            proyectados.append(base)
    return proyectados, excluidos


# --- US1: recurrencia de los movimientos manuales (quickstart escenario 2) --


def _mes_siguiente(fecha: date) -> date:
    ultimo = calendar.monthrange(fecha.year, fecha.month)[1]
    dia = min(fecha.day, ultimo)
    if fecha.month == 12:
        return fecha.replace(year=fecha.year + 1, month=1, day=dia)
    return fecha.replace(month=fecha.month + 1, day=dia)


def _anio_siguiente(fecha: date) -> date:
    ultimo = calendar.monthrange(fecha.year + 1, fecha.month)[1]
    return fecha.replace(year=fecha.year + 1, day=min(fecha.day, ultimo))


def _fechas_recurrentes(
    primera: date, hasta: date, frecuencia: FrecuenciaMovimiento
) -> list[tuple[date, int]]:
    """Ocurrencias de un movimiento recurrente dentro del rango.

    `unico` devuelve solo la fecha base; `semanal` avanza 7 dias, `mensual` al
    dia equivalente del mes siguiente (con tope al ultimo dia de meses cortos)
    y `anual` al mismo dia del ano siguiente. `orden_repeticion` numera cada
    ocurrencia.
    """
    if frecuencia is FrecuenciaMovimiento.unico:
        return [(primera, 0)]
    fechas: list[tuple[date, int]] = []
    cursor = primera
    orden = 0
    while cursor <= hasta:
        fechas.append((cursor, orden))
        orden += 1
        if frecuencia is FrecuenciaMovimiento.semanal:
            cursor = cursor + timedelta(days=7)
        elif frecuencia is FrecuenciaMovimiento.mensual:
            cursor = _mes_siguiente(cursor)
        else:
            cursor = _anio_siguiente(cursor)
    return fechas


def _origen_man(tipo: TipoMovimientoPrevision) -> OrigenMovimientoPrevision:
    if tipo is TipoMovimientoPrevision.pago:
        return OrigenMovimientoPrevision.pago_recurrente
    return OrigenMovimientoPrevision.cobro_estimado


def _expandir_manuales(
    movimientos_manuales: list[dict[str, Any]] | None,
    *,
    desde_fecha: date,
    hasta_fecha: date,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Valida y expande los movimientos manuales, replicando los recurrentes.

    Un manual sin `fecha_prevista` **no** es un error: el edge case del spec lo
    excluye de la proyeccion ("sin fecha quedan fuera") y se reporta con motivo
    `sin_fecha`, de modo que el usuario ve que tiene que datarlo (T013).
    """
    proyectados: list[dict[str, Any]] = []
    excluidos: list[dict[str, Any]] = []
    for indice, crudo in enumerate(movimientos_manuales or []):
        if not isinstance(crudo, dict):
            raise error(
                "movimiento_invalido",
                f"El movimiento manual {indice + 1} no es un objeto",
                422,
            )
        tipo = _validar_tipo(crudo.get("tipo"))
        importe = _importe(crudo.get("importe"))
        frecuencia = _frecuencia(crudo.get("frecuencia"))
        concepto = str(crudo.get("concepto") or "")[:200] or None
        base: dict[str, Any] = {
            "origen": _origen_man(tipo).value,
            "tipo": tipo.value,
            "importe": importe,
            "frecuencia": frecuencia.value,
            "concepto": concepto,
        }
        if crudo.get("fecha_prevista") in (None, ""):
            base["motivo"] = MOTIVO_SIN_FECHA
            excluidos.append(base)
            continue
        fecha = _fecha_iso(crudo["fecha_prevista"])
        for ocurrencia, orden in _fechas_recurrentes(fecha, hasta_fecha, frecuencia):
            if ocurrencia < desde_fecha or ocurrencia > hasta_fecha:
                continue
            fila = dict(base)
            fila["fecha_prevista"] = ocurrencia
            fila["orden_repeticion"] = orden
            proyectados.append(fila)
    return proyectados, excluidos


# --- US1 / T016: buckets y saldo acumulado (research D2 / SC-002) -----------


def _buckets_con_saldo(
    movimientos: list[dict[str, Any]],
    granularidad: GranularidadPrevision,
    desde_fecha: date,
    hasta_fecha: date,
    saldo_inicial: Decimal = Decimal(0),
) -> list[dict[str, Any]]:
    """Buckets ordenados con su saldo acumulado, en `Decimal` exacto.

    El acumulado arranca en `saldo_inicial` (research D2:
    `saldo_k = saldo_inicial + S(movimientos hasta k)`), de modo que el ultimo
    bucket es exactamente el `saldo_final` de la cabecera.

    Se enumeran TODOS los buckets del rango, tambien los sin movimientos, para
    que la serie temporal sea continua y el limite de solvencia en saldo cero
    sea visible (edge case del spec).
    """
    con_flujo = {
        bucket.fecha: bucket
        for bucket in agrupar_en_buckets(movimientos, granularidad.value)
    }
    filas: list[dict[str, Any]] = []
    acumulado = c4(saldo_inicial)
    for clave in enumerar_buckets(desde_fecha, hasta_fecha, granularidad.value):
        bucket = con_flujo.get(clave) or Bucket(clave)
        acumulado = c4(acumulado + bucket.neto)
        filas.append(
            {
                "fecha": clave,
                "cobros": bucket.cobros,
                "pagos": bucket.pagos,
                "neto": bucket.neto,
                "saldo_acumulado": acumulado,
            }
        )
    return filas


def _saldo_final(buckets: list[dict[str, Any]], saldo_inicial: Decimal) -> Decimal:
    """Saldo de cierre de la proyeccion: el acumulado del ultimo bucket."""
    if not buckets:
        return c4(saldo_inicial)
    return c4(buckets[-1]["saldo_acumulado"])


def _importe_persistible(valor: Any) -> Decimal:
    """Importe para un `MovimientoPrevision` (la columna exige `> 0`)."""
    importe = c4(Decimal(str(valor or 0)))
    return importe if importe > 0 else IMPORTE_MINIMO


async def _persistir_movimientos(
    db: AsyncSession,
    *,
    empresa_id: int,
    prevision_id: uuid.UUID,
    proyectados: list[dict[str, Any]],
) -> list[MovimientoPrevision]:
    """Crea los `MovimientoPrevision` incluidos (`incluido = true`)."""
    filas: list[MovimientoPrevision] = []
    for dato in proyectados:
        movimiento = MovimientoPrevision(
            empresa_id=empresa_id,
            prevision_id=prevision_id,
            origen=OrigenMovimientoPrevision(dato["origen"]),
            vencimiento_id=dato.get("vencimiento_id"),
            numero_recibo=dato.get("numero_recibo"),
            tipo=TipoMovimientoPrevision(dato["tipo"]),
            importe=_importe_persistible(dato["importe"]),
            fecha_prevista=dato["fecha_prevista"],
            frecuencia=FrecuenciaMovimiento(dato.get("frecuencia") or "unico"),
            concepto=dato.get("concepto"),
            incluido=True,
            orden_repeticion=int(dato.get("orden_repeticion") or 0),
        )
        db.add(movimiento)
        filas.append(movimiento)
    await db.flush()
    return filas


async def _persistir_excluidos(
    db: AsyncSession,
    *,
    empresa_id: int,
    prevision_id: uuid.UUID,
    excluidos: list[dict[str, Any]],
) -> None:
    """Persiste los excluidos con `incluido = false`, para su trazabilidad.

    No entran en los buckets (por definicion) pero quedan enlazados a la
    prevision con su motivo, que es lo que el detalle muestra.
    """
    for dato in excluidos:
        db.add(
            MovimientoPrevision(
                empresa_id=empresa_id,
                prevision_id=prevision_id,
                origen=OrigenMovimientoPrevision(dato["origen"]),
                vencimiento_id=dato.get("vencimiento_id"),
                numero_recibo=dato.get("numero_recibo"),
                tipo=TipoMovimientoPrevision(dato["tipo"]),
                importe=_importe_persistible(dato["importe"]),
                fecha_prevista=dato.get("fecha_prevista"),
                frecuencia=FrecuenciaMovimiento(dato.get("frecuencia") or "unico"),
                concepto=dato.get("concepto"),
                incluido=False,
                motivo_exclusion=dato["motivo"],
            )
        )
    await db.flush()


async def _proyectar(
    db: AsyncSession,
    *,
    empresa_id: int,
    prevision: PrevisionTesoreria,
    desde_fecha: date,
    hasta_fecha: date,
    granularidad: GranularidadPrevision,
    movimientos_manuales: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Nucleo compartido por `generar_prevision` y `regenerar_prevision`."""
    vencimientos, excluidos_vencimientos = await recuperar_movimientos_proyectables(
        db, empresa_id=empresa_id, desde_fecha=desde_fecha, hasta_fecha=hasta_fecha
    )
    manuales, excluidos_manuales = _expandir_manuales(
        movimientos_manuales, desde_fecha=desde_fecha, hasta_fecha=hasta_fecha
    )
    filas = await _persistir_movimientos(
        db,
        empresa_id=empresa_id,
        prevision_id=prevision.id,
        proyectados=vencimientos + manuales,
    )
    excluidos = excluidos_vencimientos + excluidos_manuales
    await _persistir_excluidos(
        db, empresa_id=empresa_id, prevision_id=prevision.id, excluidos=excluidos
    )

    saldo_inicial, origen_saldo = await saldo_tesoreria_inicial(
        db, empresa_id=empresa_id, desde_fecha=desde_fecha
    )
    buckets = _buckets_con_saldo(
        [f.__dict__ for f in filas],
        granularidad,
        desde_fecha,
        hasta_fecha,
        c4(saldo_inicial),
    )
    prevision.hasta_fecha = hasta_fecha
    prevision.granularidad = granularidad
    prevision.plan_manual = _normalizar_plan(movimientos_manuales)
    prevision.saldo_inicial = c4(saldo_inicial)
    prevision.saldo_final = _saldo_final(buckets, c4(saldo_inicial))
    prevision.origen_saldo_inicial = origen_saldo
    prevision.estado = EstadoPrevision.generada
    prevision.fecha_generacion = datetime.now(timezone.utc)
    prevision.updated_at = datetime.now(timezone.utc)
    await db.flush()

    from services.cashflow.alertas import detectar_alertas

    alertas = await detectar_alertas(
        db, empresa_id=empresa_id, prevision=prevision, buckets=buckets
    )
    return {
        "id": prevision.id,
        "prevision": prevision,
        "buckets": buckets,
        "n_movimientos": len(filas),
        "excluidos": excluidos,
        "alertas": alertas,
    }


async def generar_prevision(
    db: AsyncSession,
    *,
    empresa_id: int,
    desde_fecha: date,
    hasta_fecha: date,
    granularidad: str = "dia",
    movimientos_manuales: list[dict[str, Any]] | None = None,
    actor: str = "sistema",
) -> dict[str, Any]:
    """Genera la prevision completa: cabecera + movimientos + alertas (T016).

    Todo ocurre dentro de la transaccion abierta por `get_db`: cabecera,
    movimientos, alertas y auditoria se confirman o se revierten juntos.
    """
    _validar_rango(desde_fecha, hasta_fecha)
    grano = _granularidad(granularidad)
    numero = await proximo_numero_prevision(db, empresa_id)
    prevision = PrevisionTesoreria(
        empresa_id=empresa_id,
        numero_prevision=numero,
        desde_fecha=desde_fecha,
        hasta_fecha=hasta_fecha,
        granularidad=grano,
        saldo_inicial=Decimal(0),
        saldo_final=Decimal(0),
        estado=EstadoPrevision.generada,
        creado_por=actor,
    )
    db.add(prevision)
    await db.flush()

    resultado = await _proyectar(
        db,
        empresa_id=empresa_id,
        prevision=prevision,
        desde_fecha=desde_fecha,
        hasta_fecha=hasta_fecha,
        granularidad=grano,
        movimientos_manuales=movimientos_manuales,
    )
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        operacion="GENERAR_PREVISION",
        entidad="prevision_tesoreria",
        entidad_id=prevision.id,
        payload={
            "numero_prevision": numero,
            "granularidad": grano.value,
            "desde_fecha": desde_fecha.isoformat(),
            "hasta_fecha": hasta_fecha.isoformat(),
            "saldo_inicial": fmt(prevision.saldo_inicial),
            "saldo_final": fmt(prevision.saldo_final),
            "origen_saldo_inicial": prevision.origen_saldo_inicial,
            "n_movimientos": resultado["n_movimientos"],
            "n_excluidos": len(resultado["excluidos"]),
            "n_alertas": len(resultado["alertas"]),
        },
        usuario=actor,
    )
    return resultado


#: Origenes que el usuario introduce a mano (no se derivan de `Vencimiento`):
#: forman parte del plan de la prevision y sobreviven a una regeneracion.
ORIGENES_MANUALES: frozenset[str] = frozenset(
    {
        OrigenMovimientoPrevision.pago_recurrente.value,
        OrigenMovimientoPrevision.cobro_estimado.value,
    }
)


def _normalizar_plan(
    movimientos_manuales: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Canoniza las definiciones manuales que se guardan en el plan.

    Se guarda una fila por movimiento declarado, con el importe ya cuantizado a
    4 decimales y la fecha como ISO, para que el plan sea estable entre
    regeneraciones y auditable.
    """
    plan: list[dict[str, Any]] = []
    for indice, crudo in enumerate(movimientos_manuales or []):
        if not isinstance(crudo, dict):
            raise error(
                "movimiento_invalido",
                f"El movimiento manual {indice + 1} no es un objeto",
                422,
            )
        plan.append(
            {
                "tipo": _validar_tipo(crudo.get("tipo")).value,
                "importe": str(_importe(crudo.get("importe"))),
                "frecuencia": _frecuencia(crudo.get("frecuencia")).value,
                "concepto": (str(crudo.get("concepto") or "")[:200] or None),
                "fecha_prevista": (
                    _fecha_iso(crudo["fecha_prevista"]).isoformat()
                    if crudo.get("fecha_prevista") not in (None, "")
                    else None
                ),
            }
        )
    return plan


def _clave_plan(
    tipo: str, importe: Decimal, frecuencia: str, concepto: str | None
) -> tuple[str, str, str, str]:
    return (tipo, str(c4(importe)), frecuencia, concepto or "")


async def registrar_en_plan(
    db: AsyncSession, prevision: PrevisionTesoreria, definicion: dict[str, Any]
) -> None:
    """Anade una definicion manual al plan persistente de la prevision.

    Sin esto, el ingreso creado al atender una alerta o el pago anadido desde
    la UI se perderian en la siguiente regeneracion (el plan es la definicion
    que sobrevive al refresco de la proyeccion).
    """
    plan = [dict(d) for d in (prevision.plan_manual or [])]
    plan.append(_normalizar_plan([definicion])[0])
    prevision.plan_manual = plan
    await db.flush()


async def reprogramar_en_plan(
    db: AsyncSession,
    prevision: PrevisionTesoreria,
    *,
    tipo: str,
    importe: Decimal,
    frecuencia: str,
    concepto: str | None,
    nueva_fecha: date,
) -> None:
    """Desplaza la fecha de la definicion manual equivalente (research D6)."""
    clave = _clave_plan(tipo, importe, frecuencia, concepto)
    plan: list[dict[str, Any]] = []
    encontrada = False
    # Se reconstruye la lista y los dicts: mutar en sitio un `JSON` sin
    # `MutableList` no lo ve SQLAlchemy y el UPDATE se pierde en silencio.
    for definicion in prevision.plan_manual or []:
        copia = dict(definicion)
        if not encontrada and (
            copia.get("tipo"),
            str(c4(Decimal(str(copia.get("importe"))))),
            copia.get("frecuencia"),
            copia.get("concepto") or "",
        ) == clave:
            copia["fecha_prevista"] = nueva_fecha.isoformat()
            encontrada = True
        plan.append(copia)
    prevision.plan_manual = plan
    await db.flush()


async def regenerar_prevision(
    db: AsyncSession,
    *,
    empresa_id: int,
    prevision_id: uuid.UUID | str,
    hasta_fecha: date | None = None,
    granularidad: str | None = None,
    movimientos_manuales: list[dict[str, Any]] | None = None,
    actor: str = "sistema",
) -> dict[str, Any]:
    """Recalcula la prevision en el sitio (quickstart escenario 3, paso 3).

    La prevision es una herramienta de gestion (spec, Assumptions), no un
    documento contable: se refresca conservando su `numero_prevision`, de modo
    que la correlatividad ya emitida no se altera (constitucion IV). Se
    recalcula desde los vencimientos vigentes y se **conserva el plan manual**
    del usuario (pagos recurrentes, cobros estimados e ingresos creados al
    atender una alerta), reprogramados si hizo falta; lo actuationado queda en
    la auditoria.
    """
    prevision = await obtener_prevision(
        db, empresa_id=empresa_id, prevision_id=prevision_id
    )
    if prevision is None:
        raise error(
            "prevision_no_encontrada",
            "Prevision de tesoreria inexistente en la empresa activa",
            404,
        )
    if prevision.estado is EstadoPrevision.anulada:
        raise error("prevision_anulada", "La prevision esta anulada", 409)

    nuevo_hasta = hasta_fecha or prevision.hasta_fecha
    nuevo_grano = _granularidad(granularidad or prevision.granularidad.value)
    _validar_rango(prevision.desde_fecha, nuevo_hasta)

    plan = (
        _normalizar_plan(movimientos_manuales)
        if movimientos_manuales is not None
        else list(prevision.plan_manual or [])
    )
    await db.execute(
        delete(AlertaLiquidez).where(
            AlertaLiquidez.empresa_id == empresa_id,
            AlertaLiquidez.prevision_id == prevision.id,
        )
    )
    await db.execute(
        delete(MovimientoPrevision).where(
            MovimientoPrevision.empresa_id == empresa_id,
            MovimientoPrevision.prevision_id == prevision.id,
        )
    )
    await db.flush()

    resultado = await _proyectar(
        db,
        empresa_id=empresa_id,
        prevision=prevision,
        desde_fecha=prevision.desde_fecha,
        hasta_fecha=nuevo_hasta,
        granularidad=nuevo_grano,
        movimientos_manuales=plan,
    )
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        operacion="REGENERAR_PREVISION",
        entidad="prevision_tesoreria",
        entidad_id=prevision.id,
        payload={
            "numero_prevision": prevision.numero_prevision,
            "granularidad": nuevo_grano.value,
            "desde_fecha": prevision.desde_fecha.isoformat(),
            "hasta_fecha": nuevo_hasta.isoformat(),
            "saldo_final": fmt(prevision.saldo_final),
            "n_movimientos": resultado["n_movimientos"],
            "n_alertas": len(resultado["alertas"]),
        },
        usuario=actor,
    )
    return resultado


# --- Consultas ---------------------------------------------------------------


async def obtener_prevision(
    db: AsyncSession, *, empresa_id: int, prevision_id: uuid.UUID | str
) -> PrevisionTesoreria | None:
    """Prevision por id **dentro de la empresa activa** (constitucion III)."""
    return await db.scalar(
        select(PrevisionTesoreria).where(
            PrevisionTesoreria.empresa_id == empresa_id,
            PrevisionTesoreria.id == uuid.UUID(str(prevision_id)),
        )
    )


async def listar_previsiones(
    db: AsyncSession,
    *,
    empresa_id: int,
    estado: str | None = None,
    granularidad: str | None = None,
    desde_fecha: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """Listado paginado con filtros, siempre acotado a la empresa activa."""
    consulta = select(PrevisionTesoreria).where(
        PrevisionTesoreria.empresa_id == empresa_id
    )
    if estado:
        try:
            consulta = consulta.where(PrevisionTesoreria.estado == EstadoPrevision(estado))
        except ValueError as exc:
            raise error("estado_invalido", f"Estado no soportado: {estado!r}", 422) from exc
    if granularidad:
        consulta = consulta.where(
            PrevisionTesoreria.granularidad == _granularidad(granularidad)
        )
    if desde_fecha is not None:
        consulta = consulta.where(PrevisionTesoreria.hasta_fecha >= desde_fecha)

    total = int(await db.scalar(select(func.count()).select_from(consulta.subquery())) or 0)
    pagina = max(1, int(page))
    tamano = max(1, int(page_size))
    filas = (
        await db.scalars(
            consulta.order_by(PrevisionTesoreria.numero_prevision.desc())
            .offset((pagina - 1) * tamano)
            .limit(tamano)
        )
    ).all()
    return {"items": list(filas), "total": total, "page": pagina}


async def movimientos_de_prevision(
    db: AsyncSession,
    *,
    empresa_id: int,
    prevision_id: uuid.UUID,
    solo_incluidos: bool = True,
) -> list[MovimientoPrevision]:
    """Movimientos de la prevision ordenados por fecha y repeticion (T015)."""
    consulta = select(MovimientoPrevision).where(
        MovimientoPrevision.empresa_id == empresa_id,
        MovimientoPrevision.prevision_id == prevision_id,
    )
    if solo_incluidos:
        consulta = consulta.where(MovimientoPrevision.incluido.is_(True))
    return list(
        (
            await db.scalars(
                consulta.order_by(
                    MovimientoPrevision.fecha_prevista,
                    MovimientoPrevision.orden_repeticion,
                    MovimientoPrevision.id,
                )
            )
        ).all()
    )


def buckets_desde_movimientos(
    *, prevision: PrevisionTesoreria, movimientos: list[MovimientoPrevision]
) -> list[dict[str, Any]]:
    """Buckets + saldo acumulado de una prevision ya persistida (GET detalle)."""
    return _buckets_con_saldo(
        [m.__dict__ for m in movimientos],
        prevision.granularidad,
        prevision.desde_fecha,
        prevision.hasta_fecha,
        c4(prevision.saldo_inicial),
    )


async def detalle_prevision(
    db: AsyncSession, *, empresa_id: int, prevision_id: uuid.UUID | str
) -> dict[str, Any] | None:
    """Detalle completo: buckets con alerta, movimientos incluidos y excluidos."""
    prevision = await obtener_prevision(
        db, empresa_id=empresa_id, prevision_id=prevision_id
    )
    if prevision is None:
        return None
    movimientos = await movimientos_de_prevision(
        db, empresa_id=empresa_id, prevision_id=prevision.id, solo_incluidos=False
    )
    incluidos = [m for m in movimientos if m.incluido]
    excluidos = [m for m in movimientos if not m.incluido]
    buckets = buckets_desde_movimientos(prevision=prevision, movimientos=incluidos)

    from services.cashflow.alertas import listar_alertas

    listado = await listar_alertas(
        db, empresa_id=empresa_id, prevision_id=prevision.id
    )
    alertas = listado["items"]
    fechas_alerta = {a.fecha for a in alertas}
    for bucket in buckets:
        bucket["alerta"] = bucket["fecha"] in fechas_alerta
    return {
        "prevision": prevision,
        "buckets": buckets,
        "alertas": alertas,
        "incluidos": incluidos,
        "excluidos": excluidos,
    }


async def aplicar_movimiento_manual(
    db: AsyncSession,
    *,
    empresa_id: int,
    prevision_id: uuid.UUID,
    tipo: str,
    importe: str,
    fecha_prevista: date,
    frecuencia: str = "unico",
    concepto: str | None = None,
    actor: str = "sistema",
) -> MovimientoPrevision:
    """Alta manual de un movimiento previsto (pago recurrente / cobro estimado).

    Es la via que usa la accion `incluir_ingreso` de una alerta (research D6) y
    el alta directa desde la UI para un pago recurrente aun no vencido.
    """
    tipo_enum = _validar_tipo(tipo)
    importe_enum = _importe(importe)
    frecuencia_enum = _frecuencia(frecuencia)
    hasta = fecha_prevista if frecuencia_enum is FrecuenciaMovimiento.unico else _anio_siguiente(fecha_prevista)
    filas, _ = _expandir_manuales(
        [
            {
                "tipo": tipo_enum.value,
                "importe": importe_enum,
                "fecha_prevista": fecha_prevista,
                "frecuencia": frecuencia_enum.value,
                "concepto": concepto,
            }
        ],
        desde_fecha=fecha_prevista,
        hasta_fecha=hasta,
    )
    if not filas:
        raise error(
            "movimiento_fuera_de_rango",
            "La fecha prevista no produce ocurrencias en la prevision",
            422,
        )
    movimiento = MovimientoPrevision(
        empresa_id=empresa_id,
        prevision_id=prevision_id,
        origen=_origen_man(tipo_enum),
        tipo=tipo_enum,
        importe=importe_enum,
        fecha_prevista=filas[0]["fecha_prevista"],
        frecuencia=frecuencia_enum,
        concepto=(concepto or "")[:200] or None,
        incluido=True,
    )
    db.add(movimiento)
    await db.flush()
    if prevision_id is not None:
        prevision = await db.get(PrevisionTesoreria, prevision_id)
        if prevision is not None and prevision.empresa_id == empresa_id:
            await registrar_en_plan(
                db,
                prevision,
                {
                    "tipo": tipo_enum.value,
                    "importe": importe_enum,
                    "frecuencia": frecuencia_enum.value,
                    "concepto": concepto,
                    "fecha_prevista": filas[0]["fecha_prevista"],
                },
            )
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        operacion="ALTA_MOVIMIENTO_PREVISION",
        entidad="movimiento_prevision",
        entidad_id=movimiento.id,
        payload={
            "prevision_id": str(prevision_id),
            "tipo": tipo_enum.value,
            "importe": fmt(importe_enum),
            "fecha_prevista": movimiento.fecha_prevista.isoformat()
            if movimiento.fecha_prevista
            else None,
            "frecuencia": frecuencia_enum.value,
        },
        usuario=actor,
    )
    return movimiento
