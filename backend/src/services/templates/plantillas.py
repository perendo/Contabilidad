"""CRUD and validation for reusable accounting templates."""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.templates.linea import LineaPlantilla, PosicionLinea
from models.templates.plantilla import EstadoPlantilla, PlantillaAsiento
from models.templates.variable import TipoVariable, VariablePlantilla
from services.audit.writer import audit_escribir
from services.templates.errores import TemplateError


def _decimal(value: Any, *, field: str) -> Decimal:
    if isinstance(value, float):
        raise TemplateError("importe_invalido", f"{field} no puede ser float")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise TemplateError("importe_invalido", f"{field} no es numérico") from exc
    exponent = amount.as_tuple().exponent
    if not isinstance(exponent, int) or amount < 0 or abs(exponent) > 4:
        raise TemplateError("importe_invalido", f"{field} debe ser positivo y tener hasta 4 decimales")
    if amount == 0:
        raise TemplateError("importe_invalido", f"{field} debe ser mayor que cero")
    return amount.quantize(Decimal("0.0001"))


async def _obtener_plantilla(db: AsyncSession, empresa_id: int, plantilla_id: uuid.UUID) -> PlantillaAsiento:
    plantilla = await db.scalar(select(PlantillaAsiento).where(PlantillaAsiento.empresa_id == empresa_id, PlantillaAsiento.id == plantilla_id))
    if plantilla is None:
        raise TemplateError("plantilla_no_encontrada", "La plantilla no existe en la empresa activa", 404)
    return plantilla


async def _validar_cuenta(db: AsyncSession, empresa_id: int, cuenta_id: int) -> AccountPlan:
    cuenta = await db.scalar(select(AccountPlan).where(AccountPlan.tenant_id == empresa_id, AccountPlan.id == cuenta_id))
    if cuenta is None or not cuenta.is_active or not cuenta.is_selectable:
        raise TemplateError("cuenta_invalida", "La cuenta no existe, está inactiva o no es apuntable")
    return cuenta


async def _validar_contenido(db: AsyncSession, empresa_id: int, variables: list[dict[str, Any]], lineas: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not lineas:
        raise TemplateError("lineas_insuficientes", "La plantilla requiere al menos dos líneas")
    var_norm: list[dict[str, Any]] = []
    by_name: dict[str, uuid.UUID] = {}
    for raw in variables:
        name = str(raw.get("nombre", "")).strip()
        if not name or name in by_name:
            raise TemplateError("variable_invalida", "Las variables requieren nombres únicos")
        var_id = raw.get("id") or uuid.uuid4()
        var_id = var_id if isinstance(var_id, uuid.UUID) else uuid.UUID(str(var_id))
        by_name[name] = var_id
        var_norm.append({"id": var_id, "nombre": name, "tipo": TipoVariable.importe, "es_requerida": bool(raw.get("es_requerida", True))})
    var_ids = {v["id"] for v in var_norm}
    line_norm: list[dict[str, Any]] = []
    for index, raw in enumerate(lineas, start=1):
        try:
            cuenta_id = int(raw["cuenta_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise TemplateError("cuenta_invalida", f"Línea {index}: cuenta inválida") from exc
        await _validar_cuenta(db, empresa_id, cuenta_id)
        try:
            posicion = PosicionLinea(str(raw["posicion"]).lower())
        except ValueError as exc:
            raise TemplateError("posicion_invalida", f"Línea {index}: posición debe ser debe o haber") from exc
        fixed = raw.get("importe_fijo")
        variable_id = raw.get("variable_id")
        if fixed is not None and variable_id is not None:
            raise TemplateError("fijo_variable_excluyentes", f"Línea {index}: importe fijo y variable son excluyentes")
        if fixed is None and variable_id is None:
            raise TemplateError("importe_requerido", f"Línea {index}: falta importe fijo o variable")
        if variable_id is not None:
            variable_id = variable_id if isinstance(variable_id, uuid.UUID) else uuid.UUID(str(variable_id))
            if variable_id not in var_ids:
                raise TemplateError("variable_no_declarada", f"Línea {index}: variable no declarada")
            fixed_decimal = None
        else:
            fixed_decimal = _decimal(fixed, field=f"Línea {index}")
        line_norm.append({"id": raw.get("id") or uuid.uuid4(), "orden": int(raw.get("orden", index)), "cuenta_id": cuenta_id, "posicion": posicion, "importe_fijo": fixed_decimal, "variable_id": variable_id})
    return var_norm, line_norm


async def crear_plantilla(db: AsyncSession, *, empresa_id: int, nombre: str, descripcion: str | None, categoria: str | None, variables: list[dict[str, Any]], lineas: list[dict[str, Any]], actor: str | None = None) -> PlantillaAsiento:
    if await db.scalar(select(PlantillaAsiento).where(PlantillaAsiento.empresa_id == empresa_id, PlantillaAsiento.nombre == nombre.strip())) is not None:
        raise TemplateError("nombre_duplicado", "Ya existe una plantilla con ese nombre", 409)
    variables_norm, lineas_norm = await _validar_contenido(db, empresa_id, variables, lineas)
    plantilla = PlantillaAsiento(empresa_id=empresa_id, nombre=nombre.strip(), descripcion=descripcion, categoria=categoria, version_actual=1, estado=EstadoPlantilla.activa)
    db.add(plantilla)
    await db.flush()
    for variable in variables_norm:
        db.add(VariablePlantilla(empresa_id=empresa_id, plantilla_id=plantilla.id, **variable))
    await db.flush()
    for linea in lineas_norm:
        db.add(LineaPlantilla(empresa_id=empresa_id, plantilla_id=plantilla.id, **linea))
    await db.flush()
    await audit_escribir(db, empresa_id=empresa_id, actor=actor or "system", action="CREATE", entity="plantilla_asiento", entity_id=str(plantilla.id), payload={"nombre": plantilla.nombre})
    return plantilla


async def actualizar_plantilla(db: AsyncSession, *, empresa_id: int, plantilla_id: uuid.UUID, nombre: str | None, descripcion: str | None, categoria: str | None, variables: list[dict[str, Any]] | None, lineas: list[dict[str, Any]] | None, actor: str | None = None) -> PlantillaAsiento:
    plantilla = await _obtener_plantilla(db, empresa_id, plantilla_id)
    if nombre is not None and nombre.strip() != plantilla.nombre:
        duplicate = await db.scalar(select(PlantillaAsiento).where(PlantillaAsiento.empresa_id == empresa_id, PlantillaAsiento.nombre == nombre.strip(), PlantillaAsiento.id != plantilla_id))
        if duplicate is not None:
            raise TemplateError("nombre_duplicado", "Ya existe una plantilla con ese nombre", 409)
        plantilla.nombre = nombre.strip()
    if descripcion is not None:
        plantilla.descripcion = descripcion
    if categoria is not None:
        plantilla.categoria = categoria
    if variables is not None or lineas is not None:
        current_vars = list((await db.scalars(select(VariablePlantilla).where(VariablePlantilla.empresa_id == empresa_id, VariablePlantilla.plantilla_id == plantilla_id))).all())
        current_lines = list((await db.scalars(select(LineaPlantilla).where(LineaPlantilla.empresa_id == empresa_id, LineaPlantilla.plantilla_id == plantilla_id))).all())
        vars_input = variables if variables is not None else [{"id": v.id, "nombre": v.nombre, "es_requerida": v.es_requerida} for v in current_vars]
        lines_input = lineas if lineas is not None else [{"id": l.id, "orden": l.orden, "cuenta_id": l.cuenta_id, "posicion": l.posicion.value, "importe_fijo": l.importe_fijo, "variable_id": l.variable_id} for l in current_lines]
        vars_norm, lines_norm = await _validar_contenido(db, empresa_id, vars_input, lines_input)
        await db.execute(delete(LineaPlantilla).where(LineaPlantilla.empresa_id == empresa_id, LineaPlantilla.plantilla_id == plantilla_id))
        await db.execute(delete(VariablePlantilla).where(VariablePlantilla.empresa_id == empresa_id, VariablePlantilla.plantilla_id == plantilla_id))
        for variable in vars_norm:
            db.add(VariablePlantilla(empresa_id=empresa_id, plantilla_id=plantilla_id, **variable))
        await db.flush()
        for linea in lines_norm:
            db.add(LineaPlantilla(empresa_id=empresa_id, plantilla_id=plantilla_id, **linea))
        plantilla.version_actual += 1
    await db.flush()
    await audit_escribir(db, empresa_id=empresa_id, actor=actor or "system", action="UPDATE", entity="plantilla_asiento", entity_id=str(plantilla.id), payload={"version": plantilla.version_actual})
    return plantilla


async def cambiar_estado(db: AsyncSession, *, empresa_id: int, plantilla_id: uuid.UUID, estado: EstadoPlantilla, actor: str | None = None) -> PlantillaAsiento:
    plantilla = await _obtener_plantilla(db, empresa_id, plantilla_id)
    if plantilla.estado == estado:
        raise TemplateError("estado_duplicado", "La plantilla ya tiene ese estado", 409)
    plantilla.estado = estado
    await db.flush()
    await audit_escribir(db, empresa_id=empresa_id, actor=actor or "system", action="UPDATE", entity="plantilla_asiento", entity_id=str(plantilla.id), payload={"estado": estado.value})
    return plantilla


async def detalle_plantilla(db: AsyncSession, *, empresa_id: int, plantilla_id: uuid.UUID) -> dict[str, Any]:
    plantilla = await _obtener_plantilla(db, empresa_id, plantilla_id)
    variables = list((await db.scalars(select(VariablePlantilla).where(VariablePlantilla.empresa_id == empresa_id, VariablePlantilla.plantilla_id == plantilla_id).order_by(VariablePlantilla.nombre))).all())
    lineas = list((await db.scalars(select(LineaPlantilla).where(LineaPlantilla.empresa_id == empresa_id, LineaPlantilla.plantilla_id == plantilla_id).order_by(LineaPlantilla.orden))).all())
    return {"id": str(plantilla.id), "empresa_id": empresa_id, "nombre": plantilla.nombre, "descripcion": plantilla.descripcion, "categoria": plantilla.categoria, "version_actual": plantilla.version_actual, "estado": plantilla.estado.value, "variables": [{"id": str(v.id), "nombre": v.nombre, "tipo": v.tipo.value, "es_requerida": v.es_requerida} for v in variables], "lineas": [{"id": str(l.id), "orden": l.orden, "cuenta_id": l.cuenta_id, "posicion": l.posicion.value, "importe_fijo": f"{l.importe_fijo:0.4f}" if l.importe_fijo is not None else None, "variable_id": str(l.variable_id) if l.variable_id else None} for l in lineas]}


async def listar_plantillas(db: AsyncSession, *, empresa_id: int, estado: str | None = None, categoria: str | None = None, q: str | None = None, page: int = 1, page_size: int = 20) -> dict[str, Any]:
    filters = [PlantillaAsiento.empresa_id == empresa_id]
    if estado: filters.append(PlantillaAsiento.estado == estado)
    if categoria: filters.append(PlantillaAsiento.categoria == categoria)
    if q: filters.append(PlantillaAsiento.nombre.ilike(f"%{q}%"))
    total = await db.scalar(select(func.count()).select_from(PlantillaAsiento).where(*filters))
    rows = list((await db.scalars(select(PlantillaAsiento).where(*filters).order_by(PlantillaAsiento.nombre).offset((page - 1) * page_size).limit(page_size))).all())
    return {"items": [{"id": str(p.id), "nombre": p.nombre, "categoria": p.categoria, "version_actual": p.version_actual, "estado": p.estado.value} for p in rows], "total": int(total or 0), "page": page, "page_size": page_size}
