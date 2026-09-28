"""Preview y confirmacion de la reclasificacion de saldos (SPEC-025 US3).

T036/T037: ``preview_reclasificacion`` calcula los trasvases que el mapeo
origen -> version destino exige sobre los saldos netos POSTED del ejercicio
(SC-003); ``confirmar_reclasificacion`` los valida contra el preview, crea los
asientos ``ADJUSTMENT`` balanceados (loteados a 50 pares) y lleva cada fila de
``ReclasificacionSaldo`` por las transiciones borrador -> contabilizado ->
cuadrado, todo en la misma transaccion ACID del request (``get_db`` + flush).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.fiscal_year import FiscalYear
from models.acct.journal import JournalEntryLine, JournalEntryTipo
from models.catalog.catalogo_cuenta import CatalogoCuenta, EstadoCuentaVersion
from models.catalog.catalogo_version import CatalogoVersion, EstadoVersion
from models.catalog.mapeo_cuenta import MapeoCuenta
from models.catalog.reclasificacion_saldo import (
    EstadoReclasificacion,
    ReclasificacionSaldo,
)
from services.audit.writer import audit_escribir
from services.catalog import _comun
from services.catalog.errores import CatalogoError
from services.catalog.resolucion_historica import version_para_fecha
from services.journal.entry_service import (
    AÑO_MAX,
    AÑO_MIN,
    AsientoError,
    asentar,
    crear_borrador,
)
from services.journal.money import as_decimal, tiene_mas_de_4_decimales

__all__ = ["confirmar_reclasificacion", "preview_reclasificacion"]

_TAMANO_LOTE = 50


def _validar_ejercicio(ejercicio: int) -> None:
    if ejercicio < AÑO_MIN or ejercicio > AÑO_MAX:
        raise CatalogoError(
            "ejercicio_invalido",
            f"Ejercicio fuera de rango {AÑO_MIN}..{AÑO_MAX}: {ejercicio}",
            422,
        )


def _item_publico(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "cuenta_origen_id": item["cuenta_origen_id"],
        "codigo_origen": item["codigo_origen"],
        "importe": item["importe"],
        "cuenta_destino_id": item["cuenta_destino_id"],
        "codigo_destino": item["codigo_destino"],
        "mapeo_id": item["mapeo_id"],
    }


async def _cargar_version(
    db: AsyncSession, empresa_id: int, version_id: uuid.UUID | str
) -> CatalogoVersion:
    version = await _comun.obtener_version(db, empresa_id, version_id)
    if version is None:
        raise CatalogoError(
            "version_no_encontrada", "Version inexistente en la empresa activa", 404
        )
    if version.estado == EstadoVersion.anulada:
        raise CatalogoError(
            "version_no_activable", "Una version anulada no admite reclasificacion", 409
        )
    return version


async def _filas_version(
    db: AsyncSession, empresa_id: int, version: CatalogoVersion
) -> list[CatalogoCuenta]:
    filas = (
        await db.scalars(
            select(CatalogoCuenta).where(
                CatalogoCuenta.empresa_id == empresa_id,
                CatalogoCuenta.version_id == version.id,
            )
        )
    ).all()
    return list(filas)


async def _items_reclasificacion(
    db: AsyncSession, *, empresa_id: int, version: CatalogoVersion, ejercicio: int
) -> tuple[list[dict[str, Any]], CatalogoVersion]:
    """Trasvases pendientes: neto del ejercicio que cambia de cuenta (SC-003)."""
    origen, _fallback = await version_para_fecha(
        db, empresa_id=empresa_id, fecha=date(ejercicio, 12, 31)
    )
    if origen.id == version.id:
        return [], origen
    saldos = await _comun.saldos_ejercicio(db, empresa_id, ejercicio)
    if not saldos:
        return [], origen
    plan = {c.id: c for c in await _comun.cuentas_plan(db, empresa_id)}
    origen_por_account = {f.account_id: f for f in await _filas_version(db, empresa_id, origen)}
    destino_por_account = {f.account_id: f for f in await _filas_version(db, empresa_id, version)}
    destino_por_fila = {f.id: f for f in destino_por_account.values()}
    mapeos = (
        await db.scalars(
            select(MapeoCuenta).where(
                MapeoCuenta.empresa_id == empresa_id,
                MapeoCuenta.version_origen_id == origen.id,
                MapeoCuenta.version_destino_id == version.id,
            )
        )
    ).all()
    mapeos_por_fila = {m.cuenta_origen_id: m for m in mapeos if m.cuenta_origen_id is not None}

    items: list[dict[str, Any]] = []
    for account_id, neto in saldos.items():
        fila_origen = origen_por_account.get(account_id)
        codigo_origen_fila = (
            fila_origen.codigo_version if fila_origen is not None else str(account_id)
        )
        mapeo = mapeos_por_fila.get(fila_origen.id) if fila_origen is not None else None
        if mapeo is None:
            fila_destino = destino_por_account.get(account_id)
            if fila_destino is not None and fila_destino.estado in (
                EstadoCuentaVersion.igual,
                EstadoCuentaVersion.nueva,
            ):
                continue
            cuenta = plan.get(account_id)
            codigo = cuenta.code if cuenta is not None else str(account_id)
            raise CatalogoError(
                "sin_destino",
                (
                    f"La cuenta {codigo} tiene saldo en el ejercicio {ejercicio} "
                    "y no esta mapeada a la version destino"
                ),
                422,
            )
        if mapeo.cuenta_destino_id is None:
            raise CatalogoError(
                "sin_destino",
                (
                    f"La cuenta {codigo_origen_fila} tiene saldo y su "
                    "mapeo no tiene destino asignado"
                ),
                422,
            )
        fila_destino = destino_por_fila.get(mapeo.cuenta_destino_id)
        if fila_destino is None:  # pragma: no cover - defensivo
            raise CatalogoError(
                "sin_destino", "El destino del mapeo no existe en la version", 422
            )
        if fila_destino.account_id == account_id:
            continue
        cuenta_destino = plan.get(fila_destino.account_id)
        if cuenta_destino is None or not cuenta_destino.is_selectable:
            raise CatalogoError(
                "cuenta_destino_no_apuntable",
                f"La cuenta destino {fila_destino.codigo_version} no es apuntable",
                422,
            )
        cuenta_origen = plan.get(account_id)
        items.append(
            {
                "cuenta_origen_id": account_id,
                "codigo_origen": cuenta_origen.code if cuenta_origen is not None else str(account_id),
                "importe": _comun.importe_str(abs(neto)),
                "cuenta_destino_id": str(fila_destino.id),
                "codigo_destino": fila_destino.codigo_version,
                "mapeo_id": str(mapeo.id),
                "_neto": neto,
                "_destino_account_id": fila_destino.account_id,
            }
        )
    items.sort(key=lambda i: str(i["codigo_origen"]))
    return items, origen


async def preview_reclasificacion(
    db: AsyncSession, *, empresa_id: int, version_id: uuid.UUID | str, ejercicio: int
) -> dict[str, Any]:
    """Vista previa T036 (lectura, sin escritura): items + total."""
    _validar_ejercicio(ejercicio)
    version = await _cargar_version(db, empresa_id, version_id)
    items, origen = await _items_reclasificacion(
        db, empresa_id=empresa_id, version=version, ejercicio=ejercicio
    )
    total = sum((Decimal(i["importe"]) for i in items), Decimal(0))
    return {
        "version_id": str(version.id),
        "origen_version_id": str(origen.id),
        "items": [_item_publico(i) for i in items],
        "total_importe": _comun.importe_str(total),
    }


def _elegir_items(
    calculados: list[dict[str, Any]], items: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    """Valida la seleccion del cuerpo contra el preview (T034)."""
    if not items:
        return calculados
    por_origen = {int(i["cuenta_origen_id"]): i for i in calculados}
    elegidos: list[dict[str, Any]] = []
    vistos: set[int] = set()
    for item in items:
        crudo = item.get("cuenta_origen_id")
        if crudo is None:
            raise CatalogoError("item_invalido", "falta cuenta_origen_id", 422)
        try:
            origen_id = int(str(crudo))
        except ValueError as exc:
            raise CatalogoError(
                "item_invalido", "cuenta_origen_id invalido", 422
            ) from exc
        if origen_id in vistos:
            raise CatalogoError(
                "item_invalido", f"cuenta_origen {origen_id} duplicada", 422
            )
        vistos.add(origen_id)
        calculado = por_origen.get(origen_id)
        if calculado is None:
            raise CatalogoError(
                "item_invalido",
                f"la cuenta {origen_id} no tiene saldos reclasificables",
                422,
            )
        importe_raw = str(item.get("importe") or "")
        if tiene_mas_de_4_decimales(importe_raw):
            raise CatalogoError(
                "precision_invalida",
                f"importe con mas de 4 decimales: {importe_raw}",
                422,
            )
        if as_decimal(importe_raw) != Decimal(calculado["importe"]):
            raise CatalogoError(
                "cuadre_fallido",
                f"el importe de {calculado['codigo_origen']} no coincide con el preview",
                422,
            )
        if str(item.get("cuenta_destino_id")) != calculado["cuenta_destino_id"]:
            raise CatalogoError(
                "cuadre_fallido",
                f"el destino de {calculado['codigo_origen']} no coincide con el preview",
                422,
            )
        if str(item.get("mapeo_id")) != calculado["mapeo_id"]:
            raise CatalogoError(
                "cuadre_fallido",
                f"el mapeo de {calculado['codigo_origen']} no coincide con el preview",
                422,
            )
        elegidos.append(calculado)
    return elegidos


async def _verificar_asiento(
    db: AsyncSession, empresa_id: int, entry_id: uuid.UUID, esperado: Decimal
) -> None:
    """Debe == Haber == suma de importes del lote (constitucion I, SC-003)."""
    suma = await db.execute(
        select(
            func.coalesce(func.sum(JournalEntryLine.debe), 0),
            func.coalesce(func.sum(JournalEntryLine.haber), 0),
        ).where(
            JournalEntryLine.empresa_id == empresa_id,
            JournalEntryLine.journal_entry_id == entry_id,
        )
    )
    debe, haber = suma.one()
    if Decimal(debe) != Decimal(haber) or Decimal(debe) != esperado:
        raise CatalogoError(
            "cuadre_fallido",
            f"Asiento {entry_id} descuadrado: debe={debe} haber={haber} esperado={esperado}",
            422,
        )


async def confirmar_reclasificacion(
    db: AsyncSession,
    *,
    empresa_id: int,
    version_id: uuid.UUID | str,
    ejercicio: int,
    items: list[dict[str, Any]] | None,
    actor: str,
) -> dict[str, Any]:
    """Contabiliza los trasvases del preview (T037/FR-005, transaccion ACID)."""
    _validar_ejercicio(ejercicio)
    version = await _cargar_version(db, empresa_id, version_id)
    fiscal_year = await db.scalar(
        select(FiscalYear).where(
            FiscalYear.empresa_id == empresa_id, FiscalYear.year == ejercicio
        )
    )
    if fiscal_year is not None and fiscal_year.is_closed:
        raise CatalogoError(
            "ejercicio_cerrado",
            f"El ejercicio {ejercicio} esta cerrado: no se puede reclasificar",
            409,
        )
    calculados, _origen = await _items_reclasificacion(
        db, empresa_id=empresa_id, version=version, ejercicio=ejercicio
    )
    elegidos = _elegir_items(calculados, items)
    if not elegidos:
        await audit_escribir(
            db,
            empresa_id=empresa_id,
            actor=actor,
            action="RECLASIFICAR",
            entity="catalogo_version",
            entity_id=str(version.id),
            payload={"ejercicio": ejercicio, "reclasificaciones": 0, "asientos": []},
        )
        return {
            "reclasificaciones": 0,
            "asientos": [],
            "total_importe": _comun.importe_str(Decimal(0)),
        }

    fecha = date(ejercicio, 12, 31)
    concepto = f"Reclasificacion de saldos {version.codigo} ejercicio {ejercicio}"[:255]
    asientos_respuesta: list[dict[str, Any]] = []
    total = Decimal(0)
    creadas: list[ReclasificacionSaldo] = []
    for inicio in range(0, len(elegidos), _TAMANO_LOTE):
        lote = elegidos[inicio : inicio + _TAMANO_LOTE]
        esperado = sum((abs(i["_neto"]) for i in lote), Decimal(0))
        lineas: list[dict[str, Any]] = []
        for item in lote:
            neto = item["_neto"]
            importe = _comun.importe_str(abs(neto))
            detalle = f"{item['codigo_origen']} -> {item['codigo_destino']}"
            if neto > 0:
                lineas.append(
                    {
                        "account_id": item["_destino_account_id"],
                        "debit": importe,
                        "credit": "0.0000",
                        "detail": detalle,
                    }
                )
                lineas.append(
                    {
                        "account_id": item["cuenta_origen_id"],
                        "debit": "0.0000",
                        "credit": importe,
                        "detail": detalle,
                    }
                )
            else:
                lineas.append(
                    {
                        "account_id": item["cuenta_origen_id"],
                        "debit": importe,
                        "credit": "0.0000",
                        "detail": detalle,
                    }
                )
                lineas.append(
                    {
                        "account_id": item["_destino_account_id"],
                        "debit": "0.0000",
                        "credit": importe,
                        "detail": detalle,
                    }
                )
        try:
            borrador = await crear_borrador(
                db,
                empresa_id=empresa_id,
                fecha=fecha,
                concepto=concepto,
                lineas=lineas,
                actor=actor,
                tipo=JournalEntryTipo.ADJUSTMENT,
            )
            asiento = await asentar(
                db, empresa_id=empresa_id, entry_id=borrador.id, actor=actor
            )
        except AsientoError as exc:
            estado = 409 if exc.code in ("ejercicio_cerrado", "ejercicio_legalizado") else 422
            raise CatalogoError(exc.code, exc.message, estado) from exc
        await _verificar_asiento(db, empresa_id, asiento.id, esperado)

        filas_lote: list[ReclasificacionSaldo] = []
        for item in lote:
            fila = ReclasificacionSaldo(
                empresa_id=empresa_id,
                version_destino_id=version.id,
                mapeo_id=uuid.UUID(str(item["mapeo_id"])),
                cuenta_origen_id=item["cuenta_origen_id"],
                cuenta_destino_id=uuid.UUID(str(item["cuenta_destino_id"])),
                importe=abs(item["_neto"]),
                asiento_id=asiento.id,
                estado=EstadoReclasificacion.borrador,
            )
            db.add(fila)
            filas_lote.append(fila)
        await db.flush()
        for fila in filas_lote:
            fila.estado = EstadoReclasificacion.contabilizado
        await db.flush()
        for fila in filas_lote:
            fila.estado = EstadoReclasificacion.cuadrado
        await db.flush()
        creadas.extend(filas_lote)
        asientos_respuesta.append(
            {
                "asiento_id": str(asiento.id),
                "numero_asiento": asiento.numero_asiento,
                "cuadre": True,
            }
        )
        total += esperado

    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor,
        action="RECLASIFICAR",
        entity="catalogo_version",
        entity_id=str(version.id),
        payload={
            "ejercicio": ejercicio,
            "version_codigo": version.codigo,
            "reclasificaciones": len(creadas),
            "asientos": [a["asiento_id"] for a in asientos_respuesta],
            "total_importe": _comun.importe_str(total),
        },
    )
    return {
        "reclasificaciones": len(creadas),
        "asientos": asientos_respuesta,
        "total_importe": _comun.importe_str(total),
    }
