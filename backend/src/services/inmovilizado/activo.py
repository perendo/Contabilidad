"""Servicio alta/edición de activos de inmovilizado (SPEC-014 US1).

Valida la cuenta 21x y los grupos 681/281 del plan de la empresa activa,
calcula y valida el plan completo y persiste activo + plan en una sola
transacción ACID (el commit/rollback lo aporta el boundary ``get_db``) con
auditoría. La edición recalcula el plan futuro desde el próximo período sin
tocar asientos ``POSTED`` (constitución II, research D6).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.fiscal_year import FiscalYear
from models.inmovilizado.activo import (
    ActivoInmovilizado,
    EstadoActivo,
    MetodoAmortizacion,
)
from models.inmovilizado.plan_amortizacion import EstadoPlan, PlanAmortizacion
from services.audit.writer import audit_escribir
from services.inmovilizado.errores import error
from services.inmovilizado.plan import (
    avanzar_periodo,
    calcular_plan,
    replanear_pendientes,
)
from services.journal.money import as_decimal, tiene_mas_de_4_decimales

CUENTA_GASTO_DEFECTO = "6810"
CUENTA_ACUMULADA_PREFIJO = "28"
PAGINA_MIN, PAGINA_MAX = 1, 100


def _cuatro(value: Decimal) -> str:
    return f"{value:0.4f}"


async def _ejercicio_abierto(db: AsyncSession, empresa_id: int, anio: int, status: int) -> None:
    fy = await db.scalar(
        select(FiscalYear).where(FiscalYear.empresa_id == empresa_id, FiscalYear.year == anio)
    )
    if fy is not None and fy.is_closed:
        raise error("ejercicio_cerrado", f"El ejercicio {anio} está cerrado", status)


async def get_cuenta(db: AsyncSession, empresa_id: int, account_id: int) -> AccountPlan:
    cuenta = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id,
            AccountPlan.id == account_id,
        )
    )
    if cuenta is None:
        raise error("cuenta_no_encontrada", "La cuenta no pertenece a la empresa activa")
    if not cuenta.is_active or not cuenta.is_selectable:
        raise error("cuenta_no_apuntable", "La cuenta no es apuntable")
    return cuenta


async def get_cuenta_por_codigo(db: AsyncSession, empresa_id: int, codigo: str) -> AccountPlan:
    cuenta = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == empresa_id,
            AccountPlan.code == codigo,
            AccountPlan.is_active.is_(True),
            AccountPlan.is_selectable.is_(True),
        )
    )
    if cuenta is None:
        raise error(
            "cuenta_no_encontrada",
            f"No existe la cuenta apuntable {codigo} en la empresa activa",
        )
    return cuenta


async def resolver_cuentas(
    db: AsyncSession,
    empresa_id: int,
    cuenta_id: int,
    cuenta_gasto_id: int | None,
    cuenta_acumulada_id: int | None,
) -> tuple[AccountPlan, AccountPlan, AccountPlan]:
    cuenta = await get_cuenta(db, empresa_id, cuenta_id)
    if not cuenta.code.startswith("21"):
        raise error(
            "cuenta_invalida",
            "La cuenta del activo debe ser de inmovilizado (código que empieza por 21)",
        )
    if cuenta_gasto_id is not None:
        gasto = await get_cuenta(db, empresa_id, cuenta_gasto_id)
    else:
        gasto = await get_cuenta_por_codigo(db, empresa_id, CUENTA_GASTO_DEFECTO)

    if cuenta_acumulada_id is not None:
        acumulada = await get_cuenta(db, empresa_id, cuenta_acumulada_id)
    else:
        # 2100 -> 2810; 2180 -> 2818: "28" + las posiciones 1-2 del código
        codigo_acumulada = CUENTA_ACUMULADA_PREFIJO + cuenta.code[1:3]
        acumulada = await get_cuenta_por_codigo(db, empresa_id, codigo_acumulada)
    return cuenta, gasto, acumulada


def _validar_importes(coste: str | Decimal, vida_util: int) -> Decimal:
    if tiene_mas_de_4_decimales(str(coste)):
        raise error("precision_invalida", "coste_amortizable admite hasta 4 decimales")
    coste_dec = as_decimal(coste)
    if coste_dec <= 0:
        raise error("coste_invalido", "coste_amortizable debe ser mayor que 0")
    if vida_util <= 0:
        raise error("vida_util_invalida", "vida_util debe ser mayor que 0")
    return coste_dec


async def dar_de_alta(
    db: AsyncSession,
    *,
    empresa_id: int,
    numero_activo: str,
    cuenta_id: int,
    descripcion: str,
    fecha_alta: date,
    coste_amortizable: str | Decimal,
    vida_util: int,
    metodo: str,
    porcentaje_regresivo: str | Decimal | None = None,
    cuenta_gasto_id: int | None = None,
    cuenta_acumulada_id: int | None = None,
    actor: str = "api",
) -> dict:
    if not numero_activo or not numero_activo.strip():
        raise error("numero_activo_obligatorio", "numero_activo es obligatorio")
    desc = (descripcion or "").strip()
    if not desc:
        raise error("descripcion_obligatoria", "descripcion es obligatoria")

    coste = _validar_importes(coste_amortizable, vida_util)
    try:
        metodo_enum = MetodoAmortizacion(metodo)
    except ValueError:
        raise error("metodo_invalido", f"Método desconocido: {metodo}")
    if metodo_enum == MetodoAmortizacion.regresivo:
        if porcentaje_regresivo is None:
            raise error("porcentaje_requerido", "El método regresivo exige porcentaje_regresivo")
        pct = as_decimal(porcentaje_regresivo)
        if not (Decimal(0) < pct < Decimal(100)):
            raise error("porcentaje_invalido", "porcentaje_regresivo debe estar entre 0 y 100")
    else:
        pct = None

    await _ejercicio_abierto(db, empresa_id, fecha_alta.year, status=422)

    duplicado = await db.scalar(
        select(ActivoInmovilizado.id).where(
            ActivoInmovilizado.empresa_id == empresa_id,
            ActivoInmovilizado.numero_activo == numero_activo.strip(),
        )
    )
    if duplicado is not None:
        raise error("numero_activo_existente", "Ya existe un activo con ese numero_activo")

    cuenta, gasto, acumulada = await resolver_cuentas(
        db, empresa_id, cuenta_id, cuenta_gasto_id, cuenta_acumulada_id
    )

    plan_raw = calcular_plan(
        coste,
        vida_util,
        metodo,
        pct,
        fecha_alta,
    )

    activo = ActivoInmovilizado(
        empresa_id=empresa_id,
        numero_activo=numero_activo.strip(),
        cuenta_id=cuenta.id,
        descripcion=desc,
        fecha_alta=fecha_alta,
        coste_amortizable=coste,
        vida_util=vida_util,
        metodo=metodo_enum,
        porcentaje_regresivo=pct,
        estado=EstadoActivo.en_uso,
        cuenta_gasto_id=gasto.id,
        cuenta_acumulada_id=acumulada.id,
    )
    if activo.id is None:
        activo.id = uuid.uuid4()
    db.add(activo)
    await db.flush()

    filas = []
    for fila in plan_raw:
        pl = PlanAmortizacion(
            empresa_id=empresa_id,
            activo_id=activo.id,
            ejercicio=fila["ejercicio"],
            periodo=fila["periodo"],
            cuota=Decimal(fila["cuota"]),
            acumulado=Decimal(fila["acumulado"]),
            estado=EstadoPlan.pendiente,
        )
        db.add(pl)
        filas.append(pl)
    await db.flush()

    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor,
        action="ALTA_ACTIVO",
        entity="activo_inmovilizado",
        entity_id=str(activo.id),
        payload={
            "numero_activo": activo.numero_activo,
            "coste": _cuatro(coste),
            "metodo": metodo,
            "cuenta_id": cuenta.id,
        },
    )
    await db.flush()

    return _serializar_activo(
        activo,
        plan=[_serializar_plan(p) for p in filas],
        amortizado_acumulado=Decimal(0),
    )


async def editar_activo(
    db: AsyncSession,
    *,
    empresa_id: int,
    activo_id: uuid.UUID,
    descripcion: str | None = None,
    vida_util: int | None = None,
    coste_amortizable: str | Decimal | None = None,
    metodo: str | None = None,
    porcentaje_regresivo: str | Decimal | None = None,
    cuenta_gasto_id: int | None = None,
    cuenta_acumulada_id: int | None = None,
    actor: str = "api",
) -> dict:
    activo = await db.scalar(
        select(ActivoInmovilizado).where(
            ActivoInmovilizado.empresa_id == empresa_id,
            ActivoInmovilizado.id == activo_id,
        )
    )
    if activo is None:
        raise error("activo_no_encontrado", "Activo inexistente en la empresa activa", 404)
    if activo.estado == EstadoActivo.dado_de_baja:
        raise error("activo_dado_de_baja", "No se puede editar un activo dado de baja", 409)

    nuevo_coste = activo.coste_amortizable
    if coste_amortizable is not None:
        nuevo_coste = _validar_importes(coste_amortizable, vida_util or activo.vida_util)

    nuevo_vida = vida_util or activo.vida_util
    nuevo_metodo = metodo or activo.metodo.value
    if nuevo_metodo not in (MetodoAmortizacion.lineal.value, MetodoAmortizacion.regresivo.value):
        raise error("metodo_invalido", f"Método desconocido: {nuevo_metodo}")
    nuevo_pct: Decimal | None = activo.porcentaje_regresivo
    if porcentaje_regresivo is not None:
        nuevo_pct = as_decimal(porcentaje_regresivo)
    if nuevo_metodo == MetodoAmortizacion.regresivo.value:
        if nuevo_pct is None:
            raise error("porcentaje_requerido", "El método regresivo exige porcentaje_regresivo")
        if not (Decimal(0) < nuevo_pct < Decimal(100)):
            raise error("porcentaje_invalido", "porcentaje_regresivo debe estar entre 0 y 100")
    else:
        nuevo_pct = None

    # Acumulado ya posteado (plan amortizado) — el resto del plan DEBE caber.
    rows = (
        await db.scalars(
            select(PlanAmortizacion)
            .where(
                PlanAmortizacion.empresa_id == empresa_id,
                PlanAmortizacion.activo_id == activo.id,
            )
            .order_by(PlanAmortizacion.ejercicio, PlanAmortizacion.periodo)
        )
    ).all()
    amortizadas = [r for r in rows if r.estado == EstadoPlan.amortizado]
    pendientes = [r for r in rows if r.estado == EstadoPlan.pendiente]
    acumulado_posteado = amortizadas[-1].acumulado if amortizadas else Decimal(0)
    if nuevo_coste < acumulado_posteado:
        raise error(
            "acumulado_supera_coste",
            "El coste no puede ser inferior a la amortización ya acumulada",
            409,
        )

    if descripcion is not None:
        desc = descripcion.strip()
        if not desc:
            raise error("descripcion_obligatoria", "descripcion es obligatoria")
        activo.descripcion = desc
    activo.vida_util = nuevo_vida
    activo.coste_amortizable = nuevo_coste
    activo.metodo = MetodoAmortizacion(nuevo_metodo)
    activo.porcentaje_regresivo = nuevo_pct

    modificado_plan = any(
        [coste_amortizable is not None, vida_util is not None, metodo is not None, porcentaje_regresivo is not None]
    )
    if modificado_plan:
        await _replanear(db, empresa_id, activo, pendientes, amortizadas, acumulado_posteado)

    if cuenta_gasto_id is not None or cuenta_acumulada_id is not None:
        if activo.cuenta_gasto_id is not None and acumulado_posteado > 0 and cuenta_gasto_id != activo.cuenta_gasto_id:
            raise error("cuenta_no_editable", "No se puede cambiar la cuenta de gasto con acumulado", 409)
        if cuenta_gasto_id is not None:
            gasto = await get_cuenta(db, empresa_id, cuenta_gasto_id)
            activo.cuenta_gasto_id = gasto.id
        if cuenta_acumulada_id is not None:
            acum = await get_cuenta(db, empresa_id, cuenta_acumulada_id)
            activo.cuenta_acumulada_id = acum.id
    await db.flush()

    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor,
        action="EDICION_ACTIVO",
        entity="activo_inmovilizado",
        entity_id=str(activo.id),
        payload={
            "vida_util": activo.vida_util,
            "coste": _cuatro(activo.coste_amortizable),
            "metodo": activo.metodo.value,
            "acumulado_posteado": _cuatro(acumulado_posteado),
        },
    )
    await db.flush()

    plan_futuro = _plan_futuro(pendientes, acumulado_posteado)
    return _serializar_activo(activo, plan=plan_futuro, amortizado_acumulado=acumulado_posteado)


async def _replanear(
    db: AsyncSession,
    empresa_id: int,
    activo: ActivoInmovilizado,
    pendientes: list[PlanAmortizacion],
    amortizadas: list[PlanAmortizacion],
    acumulado_posteado: Decimal,
) -> None:
    """Recalcula la porción pendiente del plan (constitución II)."""
    restante = activo.coste_amortizable - acumulado_posteado
    n_objetivo = max(0, activo.vida_util - len(amortizadas))
    if restante <= 0:
        for r in pendientes:
            await db.delete(r)
        await db.flush()
        pendientes.clear()
        return

    # Ajustar el número de filas pendientes al nuevo horizonte de vida útil.
    if len(pendientes) > n_objetivo:
        sobrantes = pendientes[n_objetivo:]
        for r in sobrantes:
            await db.delete(r)
        del pendientes[n_objetivo:]
    elif len(pendientes) < n_objetivo:
        if pendientes:
            eje, per = avanzar_periodo(pendientes[-1].ejercicio, pendientes[-1].periodo)
        elif amortizadas:
            eje, per = avanzar_periodo(amortizadas[-1].ejercicio, amortizadas[-1].periodo)
        else:
            eje, per = activo.fecha_alta.year, activo.fecha_alta.month
        for _ in range(n_objetivo - len(pendientes)):
            nueva = PlanAmortizacion(
                empresa_id=empresa_id,
                activo_id=activo.id,
                ejercicio=eje,
                periodo=per,
                cuota=Decimal(0),
                acumulado=Decimal(0),
                estado=EstadoPlan.pendiente,
            )
            db.add(nueva)
            pendientes.append(nueva)
            eje, per = avanzar_periodo(eje, per)

    if not pendientes:
        await db.flush()
        return

    cuotas = replanear_pendientes(restante, activo.metodo.value, activo.porcentaje_regresivo, len(pendientes))
    if len(cuotas) < len(pendientes):
        sobrantes = pendientes[len(cuotas):]
        for r in sobrantes:
            await db.delete(r)
        del pendientes[len(cuotas):]

    acumulado = acumulado_posteado
    for fila, cuota in zip(pendientes, cuotas):
        acumulado += cuota
        fila.cuota = cuota
        fila.acumulado = acumulado
    await db.flush()

    if any(r.acumulado > activo.coste_amortizable or r.cuota <= 0 for r in pendientes):
        raise error("plan_excede_coste", "El plan futuro supera el coste amortizable (FR-006)")


def _plan_futuro(
    pendientes: list[PlanAmortizacion],
    acumulado_posteado: Decimal,
) -> list[dict]:
    return [
        {
            "ejercicio": p.ejercicio,
            "periodo": p.periodo,
            "cuota": _cuatro(p.cuota),
            "acumulado": _cuatro(p.acumulado),
        }
        for p in pendientes
    ]


def _serializar_plan(p: PlanAmortizacion) -> dict:
    return {
        "ejercicio": p.ejercicio,
        "periodo": p.periodo,
        "cuota": _cuatro(p.cuota),
        "acumulado": _cuatro(p.acumulado),
        "estado": p.estado.value,
    }


def _serializar_activo(
    activo: ActivoInmovilizado,
    plan: list[dict] | None = None,
    amortizado_acumulado: Decimal | None = None,
) -> dict:
    data: dict = {
        "id": str(activo.id),
        "numero_activo": activo.numero_activo,
        "cuenta_id": activo.cuenta_id,
        "descripcion": activo.descripcion,
        "fecha_alta": activo.fecha_alta.isoformat(),
        "coste_amortizable": _cuatro(activo.coste_amortizable),
        "vida_util": activo.vida_util,
        "metodo": activo.metodo.value,
        "porcentaje_regresivo": (
            f"{activo.porcentaje_regresivo:0.2f}" if activo.porcentaje_regresivo is not None else None
        ),
        "estado": activo.estado.value,
        "fecha_baja": activo.fecha_baja.isoformat() if activo.fecha_baja else None,
        "cuenta_gasto_id": activo.cuenta_gasto_id,
        "cuenta_acumulada_id": activo.cuenta_acumulada_id,
        "amortizado_acumulado": _cuatro(
            amortizado_acumulado if amortizado_acumulado is not None else Decimal(0)
        ),
    }
    if plan is not None:
        data["plan"] = plan
    return data


async def listar_activos(
    db: AsyncSession,
    *,
    empresa_id: int,
    estado: str | None = None,
    cuenta_id: int | None = None,
    ejercicio_alta: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    if not (PAGINA_MIN <= page_size <= PAGINA_MAX):
        raise error("page_size_invalido", "page_size debe estar entre 1 y 100")
    filtros = [ActivoInmovilizado.empresa_id == empresa_id]
    if estado is not None:
        if estado not in (EstadoActivo.en_uso.value, EstadoActivo.dado_de_baja.value):
            raise error("estado_invalido", f"Estado desconocido: {estado}")
        filtros.append(ActivoInmovilizado.estado == estado)
    if cuenta_id is not None:
        filtros.append(ActivoInmovilizado.cuenta_id == cuenta_id)
    if ejercicio_alta is not None:
        filtros.append(ActivoInmovilizado.fecha_alta >= date(ejercicio_alta, 1, 1))
        filtros.append(ActivoInmovilizado.fecha_alta < date(ejercicio_alta + 1, 1, 1))

    total = await db.scalar(
        select(func.count()).select_from(ActivoInmovilizado).where(*filtros)
    )
    activos = (
        await db.scalars(
            select(ActivoInmovilizado)
            .where(*filtros)
            .order_by(ActivoInmovilizado.fecha_alta, ActivoInmovilizado.numero_activo)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    items: list[dict] = []
    for activo in activos:
        acumulado = Decimal(0)
        if activos_ids := [a.id for a in activos]:
            filas = (
                await db.scalars(
                    select(PlanAmortizacion).where(
                        PlanAmortizacion.empresa_id == empresa_id,
                        PlanAmortizacion.activo_id.in_(activos_ids),
                    )
                )
            ).all()
        else:
            filas = []
        for fila in filas:
            if fila.activo_id == activo.id and fila.estado == EstadoPlan.amortizado:
                acumulado = max(acumulado, fila.acumulado)
        items.append(_serializar_activo(activo, amortizado_acumulado=acumulado))

    return {"items": items, "total": int(total or 0), "page": page, "page_size": page_size}


async def obtener_activo(
    db: AsyncSession,
    *,
    empresa_id: int,
    activo_id: uuid.UUID,
) -> dict | None:
    activo = await db.scalar(
        select(ActivoInmovilizado).where(
            ActivoInmovilizado.empresa_id == empresa_id,
            ActivoInmovilizado.id == activo_id,
        )
    )
    if activo is None:
        return None
    filas = (
        await db.scalars(
            select(PlanAmortizacion)
            .where(
                PlanAmortizacion.empresa_id == empresa_id,
                PlanAmortizacion.activo_id == activo.id,
            )
            .order_by(PlanAmortizacion.ejercicio, PlanAmortizacion.periodo)
        )
    ).all()
    acumulado = filas[-1].acumulado if filas and filas[-1].estado == EstadoPlan.amortizado else Decimal(0)
    plan = [_serializar_plan(p) for p in filas]
    return _serializar_activo(activo, plan=plan, amortizado_acumulado=acumulado)

__all__ = ["dar_de_alta", "editar_activo", "get_cuenta", "listar_activos", "obtener_activo"]