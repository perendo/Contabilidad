from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.fiscal_year import FiscalYear
from models.acct.journal import (
    JournalEntry,
    JournalEntryEstado,
    JournalEntryLine,
    JournalEntryTipo,
)
from models.fiscal.ajuste_extracontable import (
    AjusteExtracontable,
    TipoAjusteExtracontable,
)
from models.fiscal.calculo_is import CalculoIS, EstadoCalculoIS
from models.fiscal.configuracion_fiscal import ConfiguracionFiscal
from services.audit import registrar_auditoria
from services.fiscal.errores import error
from services.journal.sequence import next_numero

Q4 = Decimal("0.0001")
Q2 = Decimal("0.01")
CERO = Decimal("0.0000")
CUENTA_IMPUESTO = "6300"
CUENTA_PAGOS = "4730"
CUENTA_DIFERENCIAL_PAGAR = "4752"
CUENTA_DIFERENCIAL_DEVOLVER = "4709"
AÑO_MIN = 2000
AÑO_MAX = 2100


@dataclass(frozen=True, slots=True)
class AjusteEntrada:
    tipo: TipoAjusteExtracontable | str
    descripcion: str
    importe: Decimal | str | int
    referencia_normativa: str | None = None


AjusteLike = AjusteEntrada | Mapping[str, object]


def cuantizar_4dp(valor: Decimal | str | int) -> Decimal:
    return Decimal(str(valor)).quantize(Q4, rounding=ROUND_HALF_EVEN)


def decimal_4dp(valor: Decimal | str | int) -> Decimal:
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise error("importe_invalido", "El importe no es decimal") from exc
    if not numero.is_finite():
        raise error("importe_invalido", "El importe no es finito")
    exponent = numero.as_tuple().exponent
    if not isinstance(exponent, int) or exponent < -4:
        raise error("precision_invalida", "El importe admite como máximo 4 decimales")
    return cuantizar_4dp(numero)


def decimal_2dp(valor: Decimal | str | int) -> Decimal:
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise error("tipo_is_invalido", "El tipo impositivo no es decimal") from exc
    if not numero.is_finite():
        raise error("tipo_is_invalido", "El tipo impositivo no es finito")
    exponent = numero.as_tuple().exponent
    if not isinstance(exponent, int) or exponent < -2:
        raise error("precision_invalida", "El tipo impositivo admite como máximo 2 decimales")
    if numero <= 0 or numero > 100:
        raise error("tipo_is_invalido", "El tipo impositivo debe estar entre 0 y 100")
    return numero.quantize(Q2, rounding=ROUND_HALF_EVEN)


def _d4(valor: Decimal | str | int) -> str:
    return f"{cuantizar_4dp(valor):0.4f}"


def _d2(valor: Decimal | str | int) -> str:
    return f"{decimal_2dp(valor):0.2f}"


def _validar_ejercicio(ejercicio: int) -> None:
    if not AÑO_MIN <= ejercicio <= AÑO_MAX:
        raise error("ejercicio_invalido", "El ejercicio no es válido")


def _normalizar_tipo(valor: TipoAjusteExtracontable | str) -> TipoAjusteExtracontable:
    try:
        return TipoAjusteExtracontable(valor)
    except (TypeError, ValueError) as exc:
        raise error("tipo_ajuste_invalido", "El tipo de ajuste no es válido") from exc


def _datos_ajuste(entrada: AjusteLike) -> tuple[TipoAjusteExtracontable, str, str | None, Decimal]:
    if isinstance(entrada, AjusteEntrada):
        tipo = entrada.tipo
        descripcion = entrada.descripcion
        referencia = entrada.referencia_normativa
        importe_entrada: object = entrada.importe
    else:
        tipo_value = entrada.get("tipo")
        descripcion_value = entrada.get("descripcion")
        referencia_value = entrada.get("referencia_normativa")
        importe_entrada = entrada.get("importe")
        if not isinstance(tipo_value, (TipoAjusteExtracontable, str)):
            raise error("tipo_ajuste_invalido", "El tipo de ajuste no es válido")
        if not isinstance(descripcion_value, str):
            raise error("descripcion_invalida", "La descripción es obligatoria")
        tipo = tipo_value
        descripcion = descripcion_value
        referencia = (
            referencia_value if isinstance(referencia_value, str) else None
        )
    tipo_enum = _normalizar_tipo(tipo)
    descripcion_normalizada = descripcion.strip()
    if not descripcion_normalizada:
        raise error("descripcion_invalida", "La descripción es obligatoria")
    if referencia is not None and not referencia.strip():
        referencia = None
    if importe_entrada is None or isinstance(importe_entrada, bool):
        raise error("importe_invalido", "El importe es obligatorio")
    if not isinstance(importe_entrada, (str, int, Decimal)):
        raise error("importe_invalido", "El importe no es decimal")
    importe_decimal = decimal_4dp(importe_entrada)
    if importe_decimal <= 0:
        raise error("importe_invalido", "El importe debe ser mayor que cero")
    return tipo_enum, descripcion_normalizada, referencia, importe_decimal


async def obtener_configuracion_is(
    db: AsyncSession,
    *,
    empresa_id: int,
    actor: str | None = None,
    ip: str | None = None,
) -> ConfiguracionFiscal:
    config = await db.get(ConfiguracionFiscal, empresa_id)
    if config is not None:
        return config
    config = ConfiguracionFiscal(
        empresa_id=empresa_id,
        recargo_equivalencia_habilitado=False,
        cuenta_recargo=None,
        criterio_caja_habilitado=False,
        tipo_is=Decimal("25.00"),
        fecha_vigencia_desde=date(AÑO_MIN, 1, 1),
        fecha_vigencia_hasta=None,
        updated_at=datetime.now(timezone.utc),
    )
    db.add(config)
    await db.flush()
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        usuario=actor or "system",
        operacion="CREAR_CONFIGURACION_IS",
        entidad="configuracion_fiscal",
        entidad_id=empresa_id,
        payload={
            "tipo_is": "25.00",
            "fecha_vigencia_desde": config.fecha_vigencia_desde.isoformat(),
        },
        ip=ip,
    )
    return config


async def configurar_impuesto_sociedades(
    db: AsyncSession,
    *,
    empresa_id: int,
    tipo_is: Decimal | str | int,
    fecha_vigencia_desde: date,
    fecha_vigencia_hasta: date | None = None,
    actor: str | None = None,
    ip: str | None = None,
) -> ConfiguracionFiscal:
    if fecha_vigencia_hasta is not None and fecha_vigencia_hasta < fecha_vigencia_desde:
        raise error("vigencia_invalida", "La vigencia final es anterior a la inicial")
    tipo = decimal_2dp(tipo_is)
    config = await obtener_configuracion_is(
        db, empresa_id=empresa_id, actor=actor, ip=ip
    )
    config.tipo_is = tipo
    config.fecha_vigencia_desde = fecha_vigencia_desde
    config.fecha_vigencia_hasta = fecha_vigencia_hasta
    config.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        usuario=actor or "system",
        operacion="CONFIGURAR_IMPUESTO_SOCIEDADES",
        entidad="configuracion_fiscal",
        entidad_id=empresa_id,
        payload={
            "tipo_is": _d2(tipo),
            "fecha_vigencia_desde": fecha_vigencia_desde.isoformat(),
            "fecha_vigencia_hasta": (
                fecha_vigencia_hasta.isoformat()
                if fecha_vigencia_hasta is not None
                else None
            ),
        },
        ip=ip,
    )
    return config


async def _fiscal_year(
    db: AsyncSession, *, empresa_id: int, ejercicio: int
) -> FiscalYear | None:
    return await db.scalar(
        select(FiscalYear).where(
            FiscalYear.empresa_id == empresa_id,
            FiscalYear.year == ejercicio,
        )
    )


async def _tipo_vigente(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    actor: str | None = None,
    ip: str | None = None,
) -> Decimal:
    config = await obtener_configuracion_is(
        db, empresa_id=empresa_id, actor=actor, ip=ip
    )
    fin_ejercicio = date(ejercicio, 12, 31)
    if config.fecha_vigencia_desde > fin_ejercicio:
        raise error(
            "tipo_is_no_vigente",
            "El tipo impositivo no está vigente para el ejercicio",
        )
    if (
        config.fecha_vigencia_hasta is not None
        and config.fecha_vigencia_hasta < fin_ejercicio
    ):
        raise error(
            "tipo_is_no_vigente",
            "El tipo impositivo no está vigente para el ejercicio",
        )
    return decimal_2dp(config.tipo_is)


async def _datos_contables(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    fiscal_year: FiscalYear | None,
) -> tuple[Decimal, Decimal]:
    entradas_excluidas: set[uuid.UUID] = set()
    if fiscal_year is not None:
        if fiscal_year.regularizacion_entry_id is not None:
            entradas_excluidas.add(fiscal_year.regularizacion_entry_id)
        if fiscal_year.cierre_entry_id is not None:
            entradas_excluidas.add(fiscal_year.cierre_entry_id)
    condiciones = [
        JournalEntry.empresa_id == empresa_id,
        JournalEntry.ejercicio == ejercicio,
        JournalEntry.estado == JournalEntryEstado.POSTED,
        JournalEntryLine.empresa_id == empresa_id,
        or_(
            JournalEntryLine.cuenta.startswith("6"),
            JournalEntryLine.cuenta.startswith("7"),
            JournalEntryLine.cuenta.startswith("473"),
        ),
    ]
    if entradas_excluidas:
        condiciones.append(JournalEntry.id.not_in(entradas_excluidas))
    asientos_is = (
        select(CalculoIS.asiento_id)
        .where(
            CalculoIS.empresa_id == empresa_id,
            CalculoIS.asiento_id.is_not(None),
        )
        .scalar_subquery()
    )
    condiciones.append(JournalEntry.id.not_in(asientos_is))
    filas = (
        await db.execute(
            select(
                JournalEntryLine.cuenta,
                JournalEntryLine.debe,
                JournalEntryLine.haber,
            )
            .join(
                JournalEntry,
                JournalEntry.id == JournalEntryLine.journal_entry_id,
            )
            .where(*condiciones)
        )
    ).all()
    resultado = CERO
    pagos = CERO
    for cuenta, debe, haber in filas:
        debe_d = cuantizar_4dp(debe or 0)
        haber_d = cuantizar_4dp(haber or 0)
        if cuenta.startswith(("6", "7")):
            resultado -= debe_d - haber_d
        if cuenta.startswith("473"):
            pagos += debe_d - haber_d
    resultado_d = cuantizar_4dp(resultado)
    pagos_d = cuantizar_4dp(pagos)
    if pagos_d < 0:
        raise error(
            "pagos_a_cuenta_invalidos",
            "El saldo neto de la cuenta 473 no puede ser negativo",
        )
    return resultado_d, pagos_d


async def _agregados_ajustes(
    db: AsyncSession, *, empresa_id: int, calculo_is_id: uuid.UUID
) -> tuple[Decimal, Decimal, Decimal]:
    filas = (
        await db.scalars(
            select(AjusteExtracontable).where(
                AjusteExtracontable.empresa_id == empresa_id,
                AjusteExtracontable.calculo_is_id == calculo_is_id,
            )
        )
    ).all()
    positivos = CERO
    negativos = CERO
    reducciones = CERO
    for ajuste in filas:
        importe = cuantizar_4dp(ajuste.importe)
        if ajuste.tipo == TipoAjusteExtracontable.AJUSTE_POSITIVO:
            positivos += importe
        elif ajuste.tipo == TipoAjusteExtracontable.AJUSTE_NEGATIVO:
            negativos += importe
        else:
            reducciones += importe
    return (
        cuantizar_4dp(positivos),
        cuantizar_4dp(negativos),
        cuantizar_4dp(reducciones),
    )


def _aplicar_calculo(
    calculo: CalculoIS,
    *,
    resultado_contable: Decimal,
    pagos_a_cuenta: Decimal,
    tipo_impositivo: Decimal,
    ajustes_positivos: Decimal,
    ajustes_negativos: Decimal,
    deducciones: Decimal,
) -> None:
    base = cuantizar_4dp(
        resultado_contable + ajustes_positivos - ajustes_negativos
    )
    cuota_integra = cuantizar_4dp(base * tipo_impositivo / Decimal(100))
    cuota_liquida = cuantizar_4dp(cuota_integra - deducciones)
    calculo.resultado_contable = resultado_contable
    calculo.ajustes_positivos = ajustes_positivos
    calculo.ajustes_negativos = ajustes_negativos
    calculo.base_imponible = base
    calculo.tipo_impositivo = tipo_impositivo
    calculo.cuota_integra = cuota_integra
    calculo.deducciones = deducciones
    calculo.cuota_liquida = cuota_liquida
    calculo.pagos_a_cuenta = pagos_a_cuenta
    calculo.cuota_diferencial = cuantizar_4dp(cuota_liquida - pagos_a_cuenta)
    calculo.updated_at = datetime.now(timezone.utc)


async def _refrescar_calculo(
    db: AsyncSession,
    *,
    empresa_id: int,
    calculo: CalculoIS,
    actor: str | None = None,
    ip: str | None = None,
) -> None:
    fiscal_year = await _fiscal_year(
        db, empresa_id=empresa_id, ejercicio=calculo.ejercicio
    )
    if fiscal_year is None:
        raise error("ejercicio_no_definido", "El ejercicio no está definido")
    resultado, pagos = await _datos_contables(
        db,
        empresa_id=empresa_id,
        ejercicio=calculo.ejercicio,
        fiscal_year=fiscal_year,
    )
    tipo = await _tipo_vigente(
        db,
        empresa_id=empresa_id,
        ejercicio=calculo.ejercicio,
        actor=actor,
        ip=ip,
    )
    positivos, negativos, reducciones = await _agregados_ajustes(
        db, empresa_id=empresa_id, calculo_is_id=calculo.id
    )
    _aplicar_calculo(
        calculo,
        resultado_contable=resultado,
        pagos_a_cuenta=pagos,
        tipo_impositivo=tipo,
        ajustes_positivos=positivos,
        ajustes_negativos=negativos,
        deducciones=reducciones,
    )
    await db.flush()


async def _obtener_calculo(
    db: AsyncSession,
    *,
    empresa_id: int,
    calculo_is_id: uuid.UUID,
    bloquear: bool = False,
) -> CalculoIS | None:
    consulta = select(CalculoIS).where(
        CalculoIS.empresa_id == empresa_id,
        CalculoIS.id == calculo_is_id,
    )
    if bloquear:
        consulta = consulta.with_for_update()
    return await db.scalar(consulta)


async def _exigir_modificable(calculo: CalculoIS) -> None:
    if calculo.estado == EstadoCalculoIS.contabilizado:
        raise error("calculo_contabilizado", "El cálculo ya está contabilizado")
    if calculo.estado != EstadoCalculoIS.calculado:
        raise error("estado_invalido", "El cálculo no está en estado calculado")


async def calcular_is(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    provisional: bool = True,
    notas: str | None = None,
    actor: str | None = None,
    ip: str | None = None,
) -> CalculoIS:
    _validar_ejercicio(ejercicio)
    fiscal_year = await _fiscal_year(
        db, empresa_id=empresa_id, ejercicio=ejercicio
    )
    if fiscal_year is None:
        raise error("ejercicio_no_definido", "El ejercicio no está definido")
    if not provisional and not fiscal_year.is_closed:
        raise error(
            "ejercicio_no_cerrado",
            "El cálculo definitivo requiere un ejercicio cerrado",
        )
    definitivo = await db.scalar(
        select(CalculoIS)
        .where(
            CalculoIS.empresa_id == empresa_id,
            CalculoIS.ejercicio == ejercicio,
            CalculoIS.provisional.is_(False),
        )
        .with_for_update()
    )
    if definitivo is not None:
        raise error("calculo_ya_definitivo", "Ya existe un cálculo definitivo")
    consulta_provisional = (
        select(CalculoIS)
        .where(
            CalculoIS.empresa_id == empresa_id,
            CalculoIS.ejercicio == ejercicio,
            CalculoIS.provisional.is_(True),
        )
        .order_by(CalculoIS.created_at.desc(), CalculoIS.id.desc())
        .limit(1)
        .with_for_update()
    )
    calculo = await db.scalar(consulta_provisional)
    if calculo is not None:
        await _exigir_modificable(calculo)
        if notas is not None:
            calculo.notas = notas
    else:
        resultado, pagos = await _datos_contables(
            db,
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            fiscal_year=fiscal_year,
        )
        tipo = await _tipo_vigente(
            db,
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            actor=actor,
            ip=ip,
        )
        calculo = CalculoIS(
            id=uuid.uuid4(),
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            resultado_contable=resultado,
            ajustes_positivos=CERO,
            ajustes_negativos=CERO,
            base_imponible=resultado,
            tipo_impositivo=tipo,
            cuota_integra=CERO,
            deducciones=CERO,
            cuota_liquida=CERO,
            pagos_a_cuenta=pagos,
            cuota_diferencial=CERO,
            provisional=provisional,
            estado=EstadoCalculoIS.calculado,
            notas=notas,
            created_by=actor,
            updated_at=datetime.now(timezone.utc),
        )
    if await _agregados_ajustes(
        db, empresa_id=empresa_id, calculo_is_id=calculo.id
    ) != (CERO, CERO, CERO):
        await _refrescar_calculo(
            db,
            empresa_id=empresa_id,
            calculo=calculo,
            actor=actor,
            ip=ip,
        )
    else:
        resultado, pagos = await _datos_contables(
            db,
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            fiscal_year=fiscal_year,
        )
        tipo = await _tipo_vigente(
            db,
            empresa_id=empresa_id,
            ejercicio=ejercicio,
            actor=actor,
            ip=ip,
        )
        _aplicar_calculo(
            calculo,
            resultado_contable=resultado,
            pagos_a_cuenta=pagos,
            tipo_impositivo=tipo,
            ajustes_positivos=CERO,
            ajustes_negativos=CERO,
            deducciones=CERO,
        )
    calculo.provisional = provisional
    calculo.estado = EstadoCalculoIS.calculado
    db.add(calculo)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise error(
            "calculo_ya_definitivo", "Ya existe un cálculo definitivo"
        ) from exc
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        usuario=actor or "system",
        operacion="CALCULAR_IS",
        entidad="calculo_is",
        entidad_id=calculo.id,
        payload={
            "ejercicio": str(calculo.ejercicio),
            "provisional": calculo.provisional,
            "resultado_contable": _d4(calculo.resultado_contable),
            "base_imponible": _d4(calculo.base_imponible),
            "tipo_impositivo": _d2(calculo.tipo_impositivo),
            "cuota_integra": _d4(calculo.cuota_integra),
            "deducciones": _d4(calculo.deducciones),
            "cuota_liquida": _d4(calculo.cuota_liquida),
            "pagos_a_cuenta": _d4(calculo.pagos_a_cuenta),
            "cuota_diferencial": _d4(calculo.cuota_diferencial),
        },
        ip=ip,
    )

    return calculo


async def _crear_ajuste(
    db: AsyncSession,
    *,
    empresa_id: int,
    calculo: CalculoIS,
    entrada: AjusteLike,
) -> AjusteExtracontable:
    tipo, descripcion, referencia, importe = _datos_ajuste(entrada)
    ajuste = AjusteExtracontable(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        calculo_is_id=calculo.id,
        tipo=tipo,
        descripcion=descripcion,
        referencia_normativa=referencia,
        importe=importe,
    )
    db.add(ajuste)
    await db.flush()
    return ajuste


async def recalcular_is(
    db: AsyncSession,
    *,
    empresa_id: int,
    calculo_is_id: uuid.UUID,
    ajustes: Sequence[AjusteLike] = (),
    deducciones: Sequence[AjusteLike] = (),
    actor: str | None = None,
    ip: str | None = None,
) -> CalculoIS:
    calculo = await _obtener_calculo(
        db,
        empresa_id=empresa_id,
        calculo_is_id=calculo_is_id,
        bloquear=True,
    )
    if calculo is None:
        raise error("calculo_no_encontrado", "El cálculo no existe")
    await _exigir_modificable(calculo)
    for entrada in ajustes:
        tipo, _, _, _ = _datos_ajuste(entrada)
        if tipo not in (
            TipoAjusteExtracontable.AJUSTE_POSITIVO,
            TipoAjusteExtracontable.AJUSTE_NEGATIVO,
        ):
            raise error("tipo_ajuste_invalido", "La lista contiene una deducción")
        await _crear_ajuste(
            db, empresa_id=empresa_id, calculo=calculo, entrada=entrada
        )
    for entrada in deducciones:
        tipo, _, _, _ = _datos_ajuste(entrada)
        if tipo not in (
            TipoAjusteExtracontable.DEDUCCION,
            TipoAjusteExtracontable.BONIFICACION,
        ):
            raise error("tipo_ajuste_invalido", "La lista contiene un ajuste")
        await _crear_ajuste(
            db, empresa_id=empresa_id, calculo=calculo, entrada=entrada
        )
    await _refrescar_calculo(
        db,
        empresa_id=empresa_id,
        calculo=calculo,
        actor=actor,
        ip=ip,
    )
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        usuario=actor or "system",
        operacion="RECALCULAR_IS",
        entidad="calculo_is",
        entidad_id=calculo.id,
        payload={
            "ajustes_anadidos": len(ajustes),
            "deducciones_anadidas": len(deducciones),
            "base_imponible": _d4(calculo.base_imponible),
            "cuota_integra": _d4(calculo.cuota_integra),
            "cuota_liquida": _d4(calculo.cuota_liquida),
            "cuota_diferencial": _d4(calculo.cuota_diferencial),
        },
        ip=ip,
    )
    return calculo


async def agregar_ajuste(
    db: AsyncSession,
    *,
    empresa_id: int,
    calculo_is_id: uuid.UUID,
    tipo: TipoAjusteExtracontable | str,
    descripcion: str,
    importe: Decimal | str | int,
    referencia_normativa: str | None = None,
    actor: str | None = None,
    ip: str | None = None,
) -> AjusteExtracontable:
    calculo = await _obtener_calculo(
        db,
        empresa_id=empresa_id,
        calculo_is_id=calculo_is_id,
        bloquear=True,
    )
    if calculo is None:
        raise error("calculo_no_encontrado", "El cálculo no existe")
    await _exigir_modificable(calculo)
    ajuste = await _crear_ajuste(
        db,
        empresa_id=empresa_id,
        calculo=calculo,
        entrada=AjusteEntrada(
            tipo=tipo,
            descripcion=descripcion,
            referencia_normativa=referencia_normativa,
            importe=importe,
        ),
    )
    await _refrescar_calculo(
        db,
        empresa_id=empresa_id,
        calculo=calculo,
        actor=actor,
        ip=ip,
    )
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        usuario=actor or "system",
        operacion="AGREGAR_AJUSTE_IS",
        entidad="ajuste_extracontable",
        entidad_id=ajuste.id,
        payload={
            "calculo_is_id": str(calculo.id),
            "tipo": ajuste.tipo.value,
            "importe": _d4(ajuste.importe),
            "base_imponible": _d4(calculo.base_imponible),
            "cuota_diferencial": _d4(calculo.cuota_diferencial),
        },
        ip=ip,
    )
    return ajuste


async def eliminar_ajuste(
    db: AsyncSession,
    *,
    empresa_id: int,
    calculo_is_id: uuid.UUID,
    ajuste_id: uuid.UUID,
    actor: str | None = None,
    ip: str | None = None,
) -> None:
    calculo = await _obtener_calculo(
        db,
        empresa_id=empresa_id,
        calculo_is_id=calculo_is_id,
        bloquear=True,
    )
    if calculo is None:
        raise error("calculo_no_encontrado", "El cálculo no existe")
    await _exigir_modificable(calculo)
    ajuste = await db.scalar(
        select(AjusteExtracontable).where(
            AjusteExtracontable.empresa_id == empresa_id,
            AjusteExtracontable.calculo_is_id == calculo_is_id,
            AjusteExtracontable.id == ajuste_id,
        )
    )
    if ajuste is None:
        raise error("ajuste_no_encontrado", "El ajuste no existe")
    tipo = ajuste.tipo.value
    importe = _d4(ajuste.importe)
    await db.delete(ajuste)
    await db.flush()
    await _refrescar_calculo(
        db,
        empresa_id=empresa_id,
        calculo=calculo,
        actor=actor,
        ip=ip,
    )
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        usuario=actor or "system",
        operacion="ELIMINAR_AJUSTE_IS",
        entidad="ajuste_extracontable",
        entidad_id=ajuste_id,
        payload={
            "calculo_is_id": str(calculo.id),
            "tipo": tipo,
            "importe": importe,
            "base_imponible": _d4(calculo.base_imponible),
            "cuota_diferencial": _d4(calculo.cuota_diferencial),
        },
        ip=ip,
    )


async def obtener_calculo(
    db: AsyncSession,
    *,
    empresa_id: int,
    calculo_is_id: uuid.UUID,
) -> CalculoIS | None:
    return await _obtener_calculo(
        db, empresa_id=empresa_id, calculo_is_id=calculo_is_id
    )


async def listar_calculos(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int | None = None,
    provisional: bool | None = None,
    estado: EstadoCalculoIS | None = None,
    pagina: int = 1,
    tamano: int = 20,
) -> tuple[list[CalculoIS], int]:
    filtros = [CalculoIS.empresa_id == empresa_id]
    if ejercicio is not None:
        filtros.append(CalculoIS.ejercicio == ejercicio)
    if provisional is not None:
        filtros.append(CalculoIS.provisional.is_(provisional))
    if estado is not None:
        filtros.append(CalculoIS.estado == estado)
    total = int(
        await db.scalar(select(func.count()).select_from(CalculoIS).where(*filtros))
        or 0
    )
    filas = (
        await db.scalars(
            select(CalculoIS)
            .where(*filtros)
            .order_by(CalculoIS.ejercicio.desc(), CalculoIS.created_at.desc())
            .offset((pagina - 1) * tamano)
            .limit(tamano)
        )
    ).all()
    return list(filas), total


async def listar_ajustes(
    db: AsyncSession,
    *,
    empresa_id: int,
    calculo_is_id: uuid.UUID,
) -> list[AjusteExtracontable]:
    return list(
        (
            await db.scalars(
                select(AjusteExtracontable)
                .where(
                    AjusteExtracontable.empresa_id == empresa_id,
                    AjusteExtracontable.calculo_is_id == calculo_is_id,
                )
                .order_by(AjusteExtracontable.created_at, AjusteExtracontable.id)
            )
        ).all()
    )


def _validar_lineas_is(lineas: list[JournalEntryLine]) -> None:
    total_debe = CERO
    total_haber = CERO
    for linea in lineas:
        debe = cuantizar_4dp(linea.debe)
        haber = cuantizar_4dp(linea.haber)
        if debe < 0 or haber < 0:
            raise error("linea_no_positiva", "Las líneas deben ser positivas")
        if (debe > 0) == (haber > 0):
            raise error(
                "linea_no_positiva",
                "Cada línea debe tener solo Debe o solo Haber",
            )
        total_debe += debe
        total_haber += haber
    if total_debe <= 0 or total_haber <= 0 or total_debe != total_haber:
        raise error("asiento_desbalanceado", "El asiento del IS no cuadra")


async def _cuentas_is(
    db: AsyncSession, *, empresa_id: int, codigos: set[str]
) -> dict[str, AccountPlan]:
    filas = (
        await db.scalars(
            select(AccountPlan).where(
                AccountPlan.tenant_id == empresa_id,
                AccountPlan.code.in_(codigos),
                AccountPlan.is_selectable.is_(True),
                AccountPlan.is_active.is_(True),
            )
        )
    ).all()
    cuentas = {cuenta.code: cuenta for cuenta in filas}
    if set(cuentas) != codigos:
        faltantes = sorted(codigos - set(cuentas))
        raise error(
            "cuenta_is_no_apuntable",
            f"Cuentas IS no apuntables: {', '.join(faltantes)}",
        )
    return cuentas


def _linea(
    *,
    empresa_id: int,
    asiento_id: uuid.UUID,
    cuenta: AccountPlan,
    numero: int,
    debe: Decimal,
    haber: Decimal,
    descripcion: str,
) -> JournalEntryLine:
    return JournalEntryLine(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        journal_entry_id=asiento_id,
        account_id=cuenta.id,
        line_no=numero,
        cuenta=cuenta.code,
        debe=debe,
        haber=haber,
        descripcion=descripcion,
    )


async def contabilizar_is(
    db: AsyncSession,
    *,
    empresa_id: int,
    calculo_is_id: uuid.UUID,
    fecha_asiento: date,
    actor: str | None = None,
    ip: str | None = None,
) -> CalculoIS:
    calculo = await _obtener_calculo(
        db,
        empresa_id=empresa_id,
        calculo_is_id=calculo_is_id,
        bloquear=True,
    )
    if calculo is None:
        raise error("calculo_no_encontrado", "El cálculo no existe")
    if calculo.estado != EstadoCalculoIS.calculado:
        raise error("estado_invalido", "Solo un cálculo calculado puede contabilizarse")
    fiscal_year = await _fiscal_year(
        db, empresa_id=empresa_id, ejercicio=calculo.ejercicio
    )
    if fiscal_year is None:
        raise error("ejercicio_no_definido", "El ejercicio no está definido")
    if not fiscal_year.date_start <= fecha_asiento <= fiscal_year.date_end:
        raise error(
            "fecha_asiento_invalida",
            "La fecha del asiento pertenece a otro ejercicio",
        )
    await _refrescar_calculo(
        db,
        empresa_id=empresa_id,
        calculo=calculo,
        actor=actor,
        ip=ip,
    )
    cuota_liquida = cuantizar_4dp(calculo.cuota_liquida)
    pagos = cuantizar_4dp(calculo.pagos_a_cuenta)
    diferencial = cuantizar_4dp(calculo.cuota_diferencial)
    if cuota_liquida + abs(diferencial) <= 0:
        raise error(
            "asiento_sin_importe",
            "El cálculo no genera líneas de importe positivo",
        )
    codigos = {CUENTA_IMPUESTO}
    lineas_spec: list[tuple[str, Decimal, Decimal, str]] = []
    if cuota_liquida > 0:
        lineas_spec.append(
            (CUENTA_IMPUESTO, cuota_liquida, CERO, "Impuesto sobre beneficios")
        )
    else:
        codigos.discard(CUENTA_IMPUESTO)
    if diferencial > 0:
        if pagos > 0:
            codigos.add(CUENTA_PAGOS)
            lineas_spec.append(
                (CUENTA_PAGOS, CERO, pagos, "Pagos a cuenta del IS")
            )
        codigos.add(CUENTA_DIFERENCIAL_PAGAR)
        lineas_spec.append(
            (
                CUENTA_DIFERENCIAL_PAGAR,
                CERO,
                diferencial,
                "Cuota diferencial a pagar",
            )
        )
    elif diferencial < 0:
        if pagos > 0:
            codigos.add(CUENTA_PAGOS)
            lineas_spec.append(
                (CUENTA_PAGOS, CERO, pagos, "Pagos a cuenta del IS")
            )
        codigos.add(CUENTA_DIFERENCIAL_DEVOLVER)
        lineas_spec.append(
            (
                CUENTA_DIFERENCIAL_DEVOLVER,
                abs(diferencial),
                CERO,
                "Cuota diferencial a devolver",
            )
        )
    else:
        if pagos > 0:
            codigos.add(CUENTA_PAGOS)
            lineas_spec.append(
                (CUENTA_PAGOS, CERO, pagos, "Pagos a cuenta del IS")
            )
    cuentas = await _cuentas_is(
        db, empresa_id=empresa_id, codigos=codigos
    )
    asiento_id = uuid.uuid4()
    lineas = [
        _linea(
            empresa_id=empresa_id,
            asiento_id=asiento_id,
            cuenta=cuentas[codigo],
            numero=numero,
            debe=debe,
            haber=haber,
            descripcion=descripcion,
        )
        for numero, (codigo, debe, haber, descripcion) in enumerate(
            lineas_spec, start=1
        )
    ]
    _validar_lineas_is(lineas)
    numero_asiento = await next_numero(
        db, empresa_id, calculo.ejercicio
    )
    asiento = JournalEntry(
        id=asiento_id,
        empresa_id=empresa_id,
        ejercicio=calculo.ejercicio,
        fecha=fecha_asiento,
        tipo=JournalEntryTipo.GENERAL,
        concepto=f"Impuesto sobre sociedades {calculo.ejercicio}",
        numero_asiento=numero_asiento,
        estado=JournalEntryEstado.POSTED,
        created_by=actor,
    )
    db.add(asiento)
    await db.flush()
    db.add_all(lineas)
    await db.flush()
    calculo.estado = EstadoCalculoIS.contabilizado
    calculo.asiento_id = asiento.id
    calculo.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        usuario=actor or "system",
        operacion="CONTABILIZAR_IS",
        entidad="journal_entry",
        entidad_id=asiento.id,
        payload={
            "calculo_is_id": str(calculo.id),
            "ejercicio": str(calculo.ejercicio),
            "numero_asiento": str(numero_asiento),
            "cuota_liquida": _d4(cuota_liquida),
            "pagos_a_cuenta": _d4(pagos),
            "cuota_diferencial": _d4(diferencial),
        },
        ip=ip,
    )
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        usuario=actor or "system",
        operacion="CONTABILIZAR_IS",
        entidad="calculo_is",
        entidad_id=calculo.id,
        payload={
            "asiento_id": str(asiento.id),
            "estado": calculo.estado.value,
            "cuota_diferencial": _d4(diferencial),
        },
        ip=ip,
    )
    return calculo


def payload_ajuste(ajuste: AjusteExtracontable) -> dict[str, Any]:
    return {
        "id": str(ajuste.id),
        "tipo": ajuste.tipo.value,
        "descripcion": ajuste.descripcion,
        "referencia_normativa": ajuste.referencia_normativa,
        "importe": _d4(ajuste.importe),
    }


def payload_calculo(
    calculo: CalculoIS,
    *,
    ajustes: Sequence[AjusteExtracontable] | None = None,
) -> dict[str, Any]:
    datos: dict[str, Any] = {
        "id": str(calculo.id),
        "ejercicio": calculo.ejercicio,
        "resultado_contable": _d4(calculo.resultado_contable),
        "ajustes_positivos": _d4(calculo.ajustes_positivos),
        "ajustes_negativos": _d4(calculo.ajustes_negativos),
        "base_imponible": _d4(calculo.base_imponible),
        "tipo_impositivo": _d2(calculo.tipo_impositivo),
        "cuota_integra": _d4(calculo.cuota_integra),
        "deducciones": _d4(calculo.deducciones),
        "cuota_liquida": _d4(calculo.cuota_liquida),
        "pagos_a_cuenta": _d4(calculo.pagos_a_cuenta),
        "cuota_diferencial": _d4(calculo.cuota_diferencial),
        "provisional": calculo.provisional,
        "estado": calculo.estado.value,
        "asiento_id": (
            str(calculo.asiento_id) if calculo.asiento_id is not None else None
        ),
        "notas": calculo.notas,
        "created_at": calculo.created_at.isoformat(),
        "updated_at": calculo.updated_at.isoformat(),
    }
    if ajustes is not None:
        datos["ajustes"] = [payload_ajuste(ajuste) for ajuste in ajustes]
    return datos


def payload_configuracion(config: ConfiguracionFiscal) -> dict[str, str | None]:
    return {
        "tipo_is": _d2(config.tipo_is),
        "fecha_vigencia_desde": config.fecha_vigencia_desde.isoformat(),
        "fecha_vigencia_hasta": (
            config.fecha_vigencia_hasta.isoformat()
            if config.fecha_vigencia_hasta is not None
            else None
        ),
    }
