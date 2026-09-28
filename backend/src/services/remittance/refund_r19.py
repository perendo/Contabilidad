"""R19/C19 refund processing: parser, REVERSAL, reapertura, reclamaciones.

US3 (FR-006): procesar un rechazo/baja bancaria (AEB cuaderno 19, retorno)
generando un asiento REVERSAL balanceado (Debe 430 + 626 si gastos | Haber
572/570), reabriendo el vencimiento a pendiente y marcando el recibo devuelto.
El asiento original no se modifica (constitución II) y el identificador externo
del retorno impide reprocesados. Una devolución admite una sola reclamación
activa (FR-006, SC-004).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.journal import JournalEntry, JournalEntryLine, JournalEntryTipo
from models.ar.vencimiento import EstadoVencimiento, Vencimiento
from models.treasury.devolucion import (
    DevolucionRecibo,
    EstadoReclamacion,
    EstadoReclamacionRec,
    Reclamacion,
)
from models.treasury.recibo_remesa import ReciboEstado, ReciboRemesa
from services import accounting
from services.audit import registrar_auditoria
from services.remittance.seleccion import ejercicio_cerrado

CUENTA_CLIENTES = "430"
CUENTA_BANCO = "572"
CUENTA_GASTOS = "626"

_CODIGO_LEN = 10
_REF_LEN = 12
_FECHA_LEN = 8
_IMPORTE_LEN = 12
_MOTIVO_LEN = 40
_TIPO3_LEN = 1 + _CODIGO_LEN + 2 + _REF_LEN + _FECHA_LEN + _IMPORTE_LEN + _IMPORTE_LEN + _MOTIVO_LEN


class DevolucionError(Exception):
    status_code = 400
    code = "error"


class ReciboDevolucionNotFoundError(DevolucionError):
    status_code = 404
    code = "recibo_no_encontrado"


class DevolucionNotFoundError(DevolucionError):
    status_code = 404
    code = "devolucion_no_encontrada"


class RetornoYaProcesadoError(DevolucionError):
    status_code = 409
    code = "retorno_ya_procesado"


class DevolucionEstadoError(DevolucionError):
    status_code = 409
    code = "recibo_no_cobrado"


class DevolucionImporteError(DevolucionError):
    status_code = 422
    code = "importe_invalido"


class EjercicioCerradoDevolucionError(DevolucionError):
    status_code = 409
    code = "ejercicio_cerrado"


class FormatoRetornoError(DevolucionError):
    status_code = 422
    code = "formato_retorno_invalido"


class ReclamacionError(DevolucionError):
    status_code = 400
    code = "reclamacion_invalida"


class ReclamacionActivaError(ReclamacionError):
    status_code = 409
    code = "reclamacion_activa"


class ReclamacionEstadoError(ReclamacionError):
    status_code = 409
    code = "reclamacion_estado_no_valido"


@dataclass(frozen=True)
class RetornoR19:
    codigo: str
    clave: str
    recibo_ref: str
    fecha_cargo: date
    importe: Decimal
    importe_gastos: Decimal
    motivo: str
    identificador_externo: str
    tipo: str = "R19"


def normalizar_tipo_retorno(tipo: str) -> str:
    normalizado = tipo.strip().upper()
    if normalizado not in {"R19", "C19"}:
        raise FormatoRetornoError(f"tipo de retorno inválido: {tipo!r}")
    return normalizado


def normalizar_codigo(codigo: str) -> str:
    """Upper-case and shrink to the 10-char model column, keeping R-CUST etc."""
    normalizado = codigo.strip().upper()
    if len(normalizado) > _CODIGO_LEN:
        raise FormatoRetornoError(
            f"código de retorno demasiado largo: {codigo!r}"
        )
    return normalizado


def _parsear_fecha(value: str, campo: str) -> date:
    if len(value) != _FECHA_LEN or not value.isdigit():
        raise FormatoRetornoError(f"fecha inválida en {campo}: {value!r}")
    try:
        return datetime.strptime(value, "%Y%m%d").replace(tzinfo=timezone.utc).date()
    except ValueError as exc:
        raise FormatoRetornoError(f"fecha inválida en {campo}: {value!r}") from exc


def _parsear_centimos(value: str, campo: str) -> Decimal:
    if len(value) != _IMPORTE_LEN or not value.isdigit():
        raise FormatoRetornoError(f"importe inválido en {campo}: {value!r}")
    return Decimal(value) / Decimal(100)


def _identificador_retorno(entry: RetornoR19) -> str:
    return (
        f"{entry.tipo}:{entry.codigo}:{entry.recibo_ref}:"
        f"{entry.fecha_cargo.isoformat()}:{int(entry.importe * 100)}:"
        f"{int(entry.importe_gastos * 100)}"
    )


def parsear_retorno_aeb19(
    payload: bytes,
    *,
    tipo: str = "R19",
    encoding: str = "ISO-8859-15",
) -> list[RetornoR19]:
    """Parse an AEB cuaderno 19 R19/C19 file into normalized entries."""
    tipo_normalizado = normalizar_tipo_retorno(tipo)
    texto = payload.decode(encoding, errors="replace")
    entradas: list[RetornoR19] = []
    for linea in texto.splitlines():
        linea = linea.rstrip("\r")
        if not linea or linea[0] != "3":
            continue
        if len(linea) < _TIPO3_LEN:
            raise FormatoRetornoError(f"registro tipo 3 demasiado corto ({len(linea)})")
        codigo = normalizar_codigo(linea[1:11])
        clave = linea[11:13].strip()
        recibo_ref = linea[13:25].strip()
        fecha_cargo = _parsear_fecha(linea[25:33], "fecha_cargo")
        importe = _parsear_centimos(linea[33:45], "importe")
        importe_gastos = _parsear_centimos(linea[45:57], "importe_gastos")
        motivo = linea[57:97].strip()
        entrada = RetornoR19(
            codigo=codigo,
            clave=clave,
            recibo_ref=recibo_ref,
            fecha_cargo=fecha_cargo,
            importe=importe,
            importe_gastos=importe_gastos,
            motivo=motivo or codigo,
            identificador_externo=_identificador_retorno(
                RetornoR19(
                    codigo=codigo,
                    clave=clave,
                    recibo_ref=recibo_ref,
                    fecha_cargo=fecha_cargo,
                    importe=importe,
                    importe_gastos=importe_gastos,
                    motivo=motivo or codigo,
                    identificador_externo="",
                    tipo=tipo_normalizado,
                )
            ),
            tipo=tipo_normalizado,
        )
        entradas.append(entrada)
    return entradas


def parsear_retorno_r19(
    payload: bytes, *, encoding: str = "ISO-8859-15"
) -> list[RetornoR19]:
    """Backward-compatible R19 parser entry point."""
    return parsear_retorno_aeb19(payload, tipo="R19", encoding=encoding)


async def resolver_recibo_por_ref(
    session: AsyncSession, empresa_id: int, recibo_ref: str
) -> ReciboRemesa | None:
    resultados = list(
        (
            await session.scalars(
                select(ReciboRemesa)
                .where(
                    ReciboRemesa.empresa_id == empresa_id,
                    ReciboRemesa.recibo_num == recibo_ref,
                )
                .order_by(ReciboRemesa.fecha_cargo.desc())
            )
        ).all()
    )
    if not resultados:
        return None
    cobrados = [r for r in resultados if r.estado == ReciboEstado.cobrado]
    return cobrados[0] if cobrados else resultados[0]


def _construir_asiento_reversal(
    empresa_id: int,
    ejercicio: int,
    fecha: date,
    importe: Decimal,
    importe_gastos: Decimal,
    cuenta_banco: str,
    concepto: str,
    original_id: uuid.UUID,
) -> tuple[JournalEntry, list[JournalEntryLine]]:
    importe = Decimal(importe)
    importe_gastos = Decimal(importe_gastos)
    asiento = JournalEntry(
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        fecha=fecha,
        tipo=JournalEntryTipo.REVERSAL,
        concepto=concepto,
        original_id=original_id,
    )
    if asiento.id is None:
        asiento.id = uuid.uuid4()
    lineas = [
        JournalEntryLine(
            empresa_id=empresa_id,
            journal_entry_id=asiento.id,
            cuenta=CUENTA_CLIENTES,
            debe=importe,
            haber=Decimal(0),
            descripcion=None,
        ),
        JournalEntryLine(
            empresa_id=empresa_id,
            journal_entry_id=asiento.id,
            cuenta=cuenta_banco,
            debe=Decimal(0),
            haber=importe + importe_gastos,
            descripcion=None,
        ),
    ]
    if importe_gastos > Decimal(0):
        lineas.append(
            JournalEntryLine(
                empresa_id=empresa_id,
                journal_entry_id=asiento.id,
                cuenta=CUENTA_GASTOS,
                debe=importe_gastos,
                haber=Decimal(0),
                descripcion=None,
            )
        )
    accounting.verificar_balance(lineas)
    return asiento, lineas


async def procesar_devolucion(
    session: AsyncSession,
    empresa_id: int,
    *,
    recibo_id: uuid.UUID,
    codigo: str,
    motivo: str,
    importe: Decimal,
    importe_gastos: Decimal = Decimal(0),
    fecha_registro: date,
    fecha_cargo_original: date | None = None,
    identificador_externo: str,
    cuenta_banco: str = CUENTA_BANCO,
    usuario: str | None = None,
) -> DevolucionRecibo:
    codigo = normalizar_codigo(codigo)
    if not identificador_externo.strip():
        raise DevolucionError("identificador externo obligatorio")
    previo = await session.scalar(
        select(DevolucionRecibo.id).where(
            DevolucionRecibo.empresa_id == empresa_id,
            DevolucionRecibo.identificador_externo == identificador_externo,
        )
    )
    if previo is not None:
        raise RetornoYaProcesadoError("el retorno ya fue procesado")

    recibo = await session.scalar(
        select(ReciboRemesa).where(
            ReciboRemesa.empresa_id == empresa_id,
            ReciboRemesa.id == recibo_id,
        )
    )
    if recibo is None:
        raise ReciboDevolucionNotFoundError("recibo no encontrado")
    if recibo.estado != ReciboEstado.cobrado:
        raise DevolucionEstadoError(
            f"el recibo no está cobrado (estado={recibo.estado.value})"
        )
    if ejercicio_cerrado(empresa_id, recibo.fecha_cargo.year):
        raise EjercicioCerradoDevolucionError("el ejercicio del recibo está cerrado")

    importe = Decimal(importe)
    importe_gastos = Decimal(importe_gastos)
    if importe <= Decimal(0) or importe > recibo.importe:
        raise DevolucionImporteError(
            f"importe a revertir inválido: {importe} (cobro: {recibo.importe})"
        )
    if importe_gastos < Decimal(0):
        raise DevolucionImporteError("importe_gastos no puede ser negativo")

    vencimiento = await session.scalar(
        select(Vencimiento).where(
            Vencimiento.empresa_id == empresa_id,
            Vencimiento.id == recibo.vencimiento_id,
        )
    )
    if vencimiento is None:
        raise ReciboDevolucionNotFoundError("vencimiento no encontrado")

    fecha_cargo_original = fecha_cargo_original or recibo.fecha_cargo
    if recibo.asiento_cobro_id is None:
        raise DevolucionEstadoError("el recibo no tiene asiento de cobro asociado")

    asiento, lineas = _construir_asiento_reversal(
        empresa_id=empresa_id,
        ejercicio=recibo.fecha_cargo.year,
        fecha=fecha_registro,
        importe=importe,
        importe_gastos=importe_gastos,
        cuenta_banco=cuenta_banco,
        concepto=f"Devolución recibo {recibo.recibo_num} ({codigo})",
        original_id=recibo.asiento_cobro_id,
    )
    session.add(asiento)
    for linea in lineas:
        session.add(linea)

    devolucion = DevolucionRecibo(
        empresa_id=empresa_id,
        recibo_remesa_id=recibo.id,
        codigo=codigo,
        identificador_externo=identificador_externo,
        motivo=motivo,
        fecha_registro=fecha_registro,
        fecha_cargo_original=fecha_cargo_original,
        importe=importe,
        importe_gastos=importe_gastos,
        asiento_reversal_id=asiento.id,
        estado_reclamacion=EstadoReclamacion.sin_reclamacion,
    )
    session.add(devolucion)

    recibo.estado = ReciboEstado.devuelto
    session.add(recibo)
    vencimiento.estado = EstadoVencimiento.pendiente
    session.add(vencimiento)

    await registrar_auditoria(
        session,
        empresa_id,
        "DEVOLUCION",
        "devolucion_recibo",
        devolucion.id,
        {
            "recibo_id": str(recibo.id),
            "codigo": codigo,
            "identificador_externo": identificador_externo,
            "importe": f"{importe:f}",
            "importe_gastos": f"{importe_gastos:f}",
            "asiento_reversal_id": str(asiento.id),
            "asiento_original_id": str(recibo.asiento_cobro_id),
        },
        usuario=usuario,
    )
    await session.flush()
    return devolucion


async def gestionar_reclamacion(
    session: AsyncSession,
    empresa_id: int,
    devolucion_id: uuid.UUID,
    accion: str,
    observaciones: str | None = None,
    *,
    usuario: str | None = None,
) -> Reclamacion:
    devolucion = await session.scalar(
        select(DevolucionRecibo).where(
            DevolucionRecibo.empresa_id == empresa_id,
            DevolucionRecibo.id == devolucion_id,
        )
    )
    if devolucion is None:
        raise DevolucionNotFoundError("devolución no encontrada")

    accion = accion.strip().lower()
    reclamaciones = list(
        (
            await session.scalars(
                select(Reclamacion)
                .where(
                    Reclamacion.empresa_id == empresa_id,
                    Reclamacion.devolucion_id == devolucion.id,
                )
                .order_by(Reclamacion.fecha_registro.desc())
            )
        ).all()
    )
    activas = [
        r
        for r in reclamaciones
        if r.estado in (EstadoReclamacionRec.abierta, EstadoReclamacionRec.en_curso)
    ]
    ultima = reclamaciones[0] if reclamaciones else None

    if accion == "abrir":
        if activas:
            raise ReclamacionActivaError("ya existe una reclamación activa")
        reclamacion = Reclamacion(
            empresa_id=empresa_id,
            devolucion_id=devolucion.id,
            fecha_registro=datetime.now(timezone.utc).date(),
            estado=EstadoReclamacionRec.abierta,
            observaciones=observaciones,
        )
        devolucion.estado_reclamacion = EstadoReclamacion.reclamada
    elif accion == "en_curso":
        if ultima is None or ultima.estado != EstadoReclamacionRec.abierta:
            raise ReclamacionEstadoError("no hay reclamación abierta que avanzar")
        ultima.estado = EstadoReclamacionRec.en_curso
        reclamacion = ultima
    elif accion == "resolver":
        if ultima is None or not activas:
            raise ReclamacionEstadoError("no hay reclamación activa que resolver")
        ultima.estado = EstadoReclamacionRec.resuelta
        ultima.observaciones = observaciones or ultima.observaciones
        devolucion.estado_reclamacion = EstadoReclamacion.resuelta
        reclamacion = ultima
    elif accion == "desestimar":
        if ultima is None or not activas:
            raise ReclamacionEstadoError("no hay reclamación activa que desestimar")
        ultima.estado = EstadoReclamacionRec.desestimada
        ultima.observaciones = observaciones or ultima.observaciones
        devolucion.estado_reclamacion = EstadoReclamacion.desestimada
        reclamacion = ultima
    else:
        raise ReclamacionError(f"acción de reclamación desconocida: {accion!r}")

    if accion == "abrir":
        session.add(reclamacion)
    session.add(devolucion)

    await registrar_auditoria(
        session,
        empresa_id,
        "RECLAMACION",
        "reclamacion",
        reclamacion.id,
        {
            "devolucion_id": str(devolucion.id),
            "accion": accion,
            "estado": reclamacion.estado.value,
            "observaciones": observaciones,
        },
        usuario=usuario,
    )
    await session.flush()
    return reclamacion