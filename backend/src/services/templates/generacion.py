"""Resolve template variables and delegate accounting persistence to the journal engine."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.templates.asiento_generado import AsientoGenerado
from models.templates.linea import LineaPlantilla, PosicionLinea
from models.templates.plantilla import EstadoPlantilla, PlantillaAsiento
from models.templates.variable import VariablePlantilla
from services.audit.writer import audit_escribir
from services.journal.motor import crear_asiento_multilinea, obtener_asiento
from services.templates.errores import TemplateError


async def generar_asiento(
    db: AsyncSession,
    *,
    empresa_id: int,
    plantilla_id: uuid.UUID,
    fecha: date,
    variables: dict[str, Any],
    concepto: str | None = None,
    actor: str | None = None,
    usuario_id: int | None = None,
) -> dict[str, Any]:
    plantilla = await db.scalar(select(PlantillaAsiento).where(PlantillaAsiento.empresa_id == empresa_id, PlantillaAsiento.id == plantilla_id))
    if plantilla is None:
        raise TemplateError("plantilla_no_encontrada", "La plantilla no existe en la empresa activa", 404)
    if plantilla.estado != EstadoPlantilla.activa:
        raise TemplateError("plantilla_inactiva", "La plantilla está inactiva", 409)
    vars_db = list((await db.scalars(select(VariablePlantilla).where(VariablePlantilla.empresa_id == empresa_id, VariablePlantilla.plantilla_id == plantilla_id))).all())
    supplied: dict[uuid.UUID, Decimal] = {}
    supplied_json: dict[str, str] = {}
    for variable in vars_db:
        raw = variables.get(str(variable.id), variables.get(variable.nombre))
        if raw in (None, ""):
            if variable.es_requerida:
                raise TemplateError("variables_faltantes", f"Falta la variable {variable.nombre}")
            continue
        if isinstance(raw, float):
            raise TemplateError("variable_no_numerica", f"La variable {variable.nombre} no puede ser float")
        try:
            value = Decimal(str(raw))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise TemplateError("variable_no_numerica", f"La variable {variable.nombre} no es numérica") from exc
        exponent = value.as_tuple().exponent
        if not isinstance(exponent, int) or value < 0 or abs(exponent) > 4:
            raise TemplateError("variable_invalida", f"La variable {variable.nombre} tiene precisión o signo inválidos")
        value = value.quantize(Decimal("0.0001"))
        supplied[variable.id] = value
        supplied_json[str(variable.id)] = f"{value:0.4f}"
    lines = list((await db.scalars(select(LineaPlantilla).where(LineaPlantilla.empresa_id == empresa_id, LineaPlantilla.plantilla_id == plantilla_id).order_by(LineaPlantilla.orden))).all())
    resolved: list[dict[str, Any]] = []
    for line in lines:
        amount = line.importe_fijo
        if amount is None and line.variable_id is not None:
            amount = supplied.get(line.variable_id)
        if amount is None:
            continue
        cuenta = await db.scalar(
            select(AccountPlan).where(
                AccountPlan.tenant_id == empresa_id,
                AccountPlan.id == line.cuenta_id,
                AccountPlan.is_active.is_(True),
                AccountPlan.is_selectable.is_(True),
            )
        )
        if cuenta is None:
            raise TemplateError("cuenta_invalida", "La cuenta de la plantilla no está disponible")
        resolved.append({"cuenta": cuenta.code, "debe": amount if line.posicion == PosicionLinea.debe else Decimal(0), "haber": amount if line.posicion == PosicionLinea.haber else Decimal(0)})
    if len(resolved) < 2:
        raise TemplateError("lineas_insuficientes", "La plantilla no produce suficientes líneas", 409)
    try:
        asiento = await crear_asiento_multilinea(db, empresa_id=empresa_id, fecha=fecha, concepto=concepto or plantilla.nombre, lineas=resolved, actor=actor)
    except Exception as exc:
        code = getattr(exc, "code", "plantilla_no_cuadra")
        message = getattr(exc, "message", str(exc))
        raise TemplateError(code, message, 409 if code in ("desbalanceo", "ejercicio_cerrado", "ejercicio_invalido") else 422) from exc
    generado = AsientoGenerado(empresa_id=empresa_id, asiento_id=asiento.id, plantilla_id=plantilla.id, version_plantilla=plantilla.version_actual, variables_aportadas=supplied_json, fecha_generacion=datetime.now(timezone.utc), usuario_generador=usuario_id)
    db.add(generado)
    await db.flush()
    await audit_escribir(db, empresa_id=empresa_id, actor=actor or "system", action="GENERATE_TEMPLATE_ENTRY", entity="asiento_generado", entity_id=str(asiento.id), payload={"plantilla_id": str(plantilla.id), "version": plantilla.version_actual, "variables": supplied_json})
    dto = await obtener_asiento(db, empresa_id=empresa_id, entry_id=asiento.id)
    return {"asiento_id": str(asiento.id), "plantilla_id": str(plantilla.id), "version_plantilla": plantilla.version_actual, "variables_aportadas": supplied_json, "asiento": dto}


async def listar_generados(db: AsyncSession, *, empresa_id: int, plantilla_id: uuid.UUID) -> dict[str, Any]:
    rows = list((await db.scalars(select(AsientoGenerado).where(AsientoGenerado.empresa_id == empresa_id, AsientoGenerado.plantilla_id == plantilla_id).order_by(AsientoGenerado.fecha_generacion))).all())
    return {"items": [{"asiento_id": str(row.asiento_id), "plantilla_id": str(row.plantilla_id), "version_plantilla": row.version_plantilla, "fecha_generacion": row.fecha_generacion.isoformat(), "variables_aportadas": row.variables_aportadas} for row in rows], "total": len(rows), "page": 1, "page_size": len(rows) or 20}
