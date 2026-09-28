"""Internos compartidos del catalogo versionado (SPEC-025).

Concentra creacion de versiones, proyeccion de cuentas por version, aplicacion
de operaciones (altas/renombrados/bajas), generacion de mapeos, calculo de
saldos y deteccion de solapes. Lo importan ``registro_version`` e
``importacion_catalogo`` (nunca al reves) para evitar ciclos de importacion.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.acct.journal import JournalEntry, JournalEntryEstado, JournalEntryLine
from models.catalog.catalogo_cuenta import CatalogoCuenta, EstadoCuentaVersion
from models.catalog.catalogo_version import CatalogoVersion, EstadoVersion
from models.catalog.mapeo_cuenta import MapeoCuenta, OrigenMapeo, TipoMovimiento
from models.iam.company import Company
from services.catalog.errores import CatalogoError

__all__ = [
    "aplicar_operaciones",
    "asegurar_cuenta_plan",
    "asegurar_sin_solape",
    "contar_version",
    "crear_mapeo",
    "crear_version_completa",
    "cuentas_plan",
    "importe_str",
    "mapeos_igualdad",
    "nivel_de",
    "obtener_version",
    "pendientes_mapeo",
    "proyectar_base",
    "saldo_total",
    "saldos_ejercicio",
    "siguiente_numero",
    "validar_codigo",
    "version_base",
]


def importe_str(valor: Decimal) -> str:
    """Importe como string de 4 decimales (contrato: nunca coma flotante)."""
    return f"{valor:.4f}"


def validar_codigo(codigo: str | None, campo: str = "codigo") -> str:
    """Codigo de cuenta: solo digitos, hasta 8 caracteres (422 si no)."""
    if not codigo or not codigo.isdigit() or len(codigo) > 8:
        raise CatalogoError(
            "codigo_invalido", f"{campo} invalido: {codigo!r}", 422
        )
    return codigo


def nivel_de(codigo: str) -> int:
    """Nivel PGC equivalente: 1-4 por longitud, subcuentas largas nivel 5."""
    return len(codigo) if len(codigo) <= 4 else 5


async def asegurar_sin_solape(
    db: AsyncSession,
    empresa_id: int,
    fecha_inicio: date,
    fecha_fin: date | None,
    *,
    excluir_id: uuid.UUID | None = None,
) -> None:
    """FR-006/SC-004: ninguna otra version no anulada solapa la vigencia."""
    consulta = select(CatalogoVersion).where(
        CatalogoVersion.empresa_id == empresa_id,
        CatalogoVersion.estado != EstadoVersion.anulada,
        CatalogoVersion.fecha_inicio <= (fecha_fin or date.max),
        func.coalesce(CatalogoVersion.fecha_fin, date.max) >= fecha_inicio,
    )
    if excluir_id is not None:
        consulta = consulta.where(CatalogoVersion.id != excluir_id)
    otra = (await db.scalars(consulta)).first()
    if otra is not None:
        raise CatalogoError(
            "solape_vigencia",
            (
                f"La vigencia {fecha_inicio.isoformat()}.."
                f"{fecha_fin.isoformat() if fecha_fin else 'NULL'} se solapa con "
                f"la version {otra.numero_version} ({otra.codigo})"
            ),
            422,
        )


async def siguiente_numero(db: AsyncSession, empresa_id: int) -> int:
    """numero_version correlativo por empresa bajo SELECT ... FOR UPDATE."""
    await db.execute(
        select(Company.company_id)
        .where(Company.company_id == empresa_id)
        .with_for_update()
    )
    maximo = await db.scalar(
        select(func.max(CatalogoVersion.numero_version)).where(
            CatalogoVersion.empresa_id == empresa_id
        )
    )
    return int(maximo or 0) + 1


async def cuentas_plan(db: AsyncSession, empresa_id: int) -> list[AccountPlan]:
    """Plan de cuentas completo de la empresa ordenado por nivel y codigo."""
    filas = (
        await db.scalars(
            select(AccountPlan)
            .where(AccountPlan.tenant_id == empresa_id)
            .order_by(AccountPlan.level, AccountPlan.code)
        )
    ).all()
    return list(filas)


async def obtener_version(
    db: AsyncSession, empresa_id: int, version_id: uuid.UUID | str
) -> CatalogoVersion | None:
    """Version por id acotada a la empresa activa (None si no existe o cruza)."""
    try:
        ident = version_id if isinstance(version_id, uuid.UUID) else uuid.UUID(str(version_id))
    except (ValueError, TypeError, AttributeError):
        return None
    version = await db.get(CatalogoVersion, ident)
    if version is None or version.empresa_id != empresa_id:
        return None
    return version


async def version_base(
    db: AsyncSession, empresa_id: int, *, hasta_numero: int | None = None
) -> CatalogoVersion | None:
    """Ultima version no anulada anterior a ``hasta_numero`` (la base)."""
    consulta = select(CatalogoVersion).where(
        CatalogoVersion.empresa_id == empresa_id,
        CatalogoVersion.estado != EstadoVersion.anulada,
    )
    if hasta_numero is not None:
        consulta = consulta.where(CatalogoVersion.numero_version < hasta_numero)
    return await db.scalar(consulta.order_by(CatalogoVersion.numero_version.desc()).limit(1))


async def crear_version_completa(
    db: AsyncSession,
    *,
    empresa_id: int,
    codigo: str,
    fecha_inicio: date,
    fecha_fin: date | None,
    operaciones: list[dict[str, Any]],
    mapeo_explicito: list[dict[str, Any]],
    actor: str,
    es_migracion: bool = False,
) -> CatalogoVersion:
    """Crea la version (borrador), proyecta la base y aplica operaciones.

    Todo en la misma transaccion ACID del request (``get_db`` + ``flush``);
    ``numero_version`` se asigna con bloqueo ``FOR UPDATE`` sobre la empresa
    (constitucion IV) y el solape se rechaza en servicio y en trigger.
    """
    if not codigo or not codigo.strip():
        raise CatalogoError("codigo_invalido", "El codigo de version es obligatorio", 422)
    if fecha_fin is not None and fecha_fin < fecha_inicio:
        raise CatalogoError(
            "rango_invalido", "fecha_fin no puede ser anterior a fecha_inicio", 422
        )
    await asegurar_sin_solape(db, empresa_id, fecha_inicio, fecha_fin)
    version = CatalogoVersion(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        numero_version=await siguiente_numero(db, empresa_id),
        codigo=codigo.strip(),
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        estado=EstadoVersion.borrador,
        es_migracion=es_migracion,
        creado_por=actor,
    )
    db.add(version)
    await db.flush()

    plan = {c.code: c for c in await cuentas_plan(db, empresa_id)}
    base = await version_base(db, empresa_id, hasta_numero=version.numero_version)
    proyeccion = await proyectar_base(
        db, empresa_id=empresa_id, version=version, base=base, plan=plan
    )
    await aplicar_operaciones(
        db,
        empresa_id=empresa_id,
        version=version,
        base=base,
        proyeccion=proyeccion,
        plan=plan,
        operaciones=operaciones,
        mapeo_explicito=mapeo_explicito,
    )
    await mapeos_igualdad(
        db, empresa_id=empresa_id, version=version, base=base, proyeccion=proyeccion
    )
    await db.flush()
    return version


async def asegurar_cuenta_plan(
    db: AsyncSession,
    *,
    empresa_id: int,
    codigo: str,
    nombre: str,
    padre_codigo: str | None,
    plan: dict[str, AccountPlan],
) -> AccountPlan:
    """Devuelve la cuenta del plan (la crea si no existe) validando estructura.

    El padre debe existir en el plan (el seed PGC minimo lo garantiza); si no,
    responde 422 ``padre_no_encontrado``. Nivel y prefijo se validan aqui para
    que los triggers SPEC-001 nunca fallen con un 500.
    """
    validar_codigo(codigo)
    existente = plan.get(codigo)
    if existente is not None:
        return existente
    nivel = nivel_de(codigo)
    if nivel == 1:
        derivado: str | None = None
    else:
        derivado = codigo[:-1] if nivel <= 4 else codigo[:4]
    if padre_codigo is not None and nivel > 1:
        validar_codigo(padre_codigo, "padre_codigo")
        if padre_codigo != derivado:
            raise CatalogoError(
                "padre_invalido",
                f"El padre {padre_codigo} no es el prefijo valido de {codigo}",
                422,
            )
    padre: AccountPlan | None = None
    if derivado is not None:
        padre = plan.get(derivado)
        if padre is None:
            raise CatalogoError(
                "padre_no_encontrado",
                f"La cuenta padre {derivado} de {codigo} no existe en el plan",
                422,
            )
        if not padre.is_active:
            raise CatalogoError(
                "padre_inactivo", f"La cuenta padre {derivado} esta inactiva", 422
            )
        if padre.level != nivel - 1:
            raise CatalogoError(
                "padre_invalido", f"El padre {derivado} tiene nivel inesperado", 422
            )
    cuenta = AccountPlan(
        tenant_id=empresa_id,
        code=codigo,
        name=nombre or f"Cuenta {codigo}",
        parent_id=padre.id if padre is not None else None,
        level=nivel,
        is_selectable=nivel >= 4,
        is_active=True,
    )
    db.add(cuenta)
    await db.flush()
    if padre is not None and padre.is_selectable:
        padre.is_selectable = False
        await db.flush()
    plan[codigo] = cuenta
    return cuenta


async def _cuerpo_proyeccion(
    db: AsyncSession, empresa_id: int, base: CatalogoVersion
) -> list[CatalogoCuenta]:
    """Miembros de la version base: excluye suprimidas y renombradas fuera."""
    filas = (
        await db.scalars(
            select(CatalogoCuenta).where(
                CatalogoCuenta.empresa_id == empresa_id,
                CatalogoCuenta.version_id == base.id,
                CatalogoCuenta.estado.not_in(
                    (EstadoCuentaVersion.suprimida, EstadoCuentaVersion.renombrada)
                ),
            )
        )
    ).all()
    return list(filas)


async def proyectar_base(
    db: AsyncSession,
    *,
    empresa_id: int,
    version: CatalogoVersion,
    base: CatalogoVersion | None,
    plan: dict[str, AccountPlan],
) -> dict[int, CatalogoCuenta]:
    """Crea las filas ``igual`` de la version a partir de la base (FR-001).

    Sin version base se proyecta todo el plan. Los ids se asignan antes de
    enlazar ``parent_version_id`` (FK auto-referente) y se hace ``flush`` por
    niveles para respetar el orden de insercion.
    """
    plan_por_id = {c.id: c for c in plan.values()}
    if base is None:
        datos: list[tuple[int, str, str, int]] = [
            (c.id, c.code, c.name, c.level) for c in plan.values()
        ]
    else:
        miembros = await _cuerpo_proyeccion(db, empresa_id, base)
        datos = []
        for cc in miembros:
            cuenta = plan_por_id.get(cc.account_id)
            if cuenta is None:
                continue
            datos.append(
                (cc.account_id, cc.codigo_version, cc.nombre_version, cuenta.level)
            )
    datos.sort(key=lambda d: (d[3], d[1]))
    por_account: dict[int, CatalogoCuenta] = {}
    nivel_actual: int | None = None
    for account_id, codigo, nombre, nivel in datos:
        cuenta_plan = plan_por_id.get(account_id)
        if cuenta_plan is None:  # pragma: no cover - defensivo
            continue
        if nivel_actual is not None and nivel != nivel_actual:
            await db.flush()
        nivel_actual = nivel
        parent_row = (
            por_account.get(cuenta_plan.parent_id)
            if cuenta_plan.parent_id is not None
            else None
        )
        fila = CatalogoCuenta(
            id=uuid.uuid4(),
            empresa_id=empresa_id,
            version_id=version.id,
            account_id=account_id,
            codigo_version=codigo,
            nombre_version=nombre,
            estado=EstadoCuentaVersion.igual,
            parent_version_id=parent_row.id if parent_row is not None else None,
        )
        db.add(fila)
        por_account[account_id] = fila
    await db.flush()
    return por_account


async def crear_mapeo(
    db: AsyncSession,
    *,
    empresa_id: int,
    version_origen_id: uuid.UUID,
    version_destino_id: uuid.UUID,
    cuenta_origen_id: uuid.UUID,
    cuenta_destino_id: uuid.UUID | None,
    tipo: TipoMovimiento,
    requiere_reclasificacion: bool,
    origen: OrigenMapeo = OrigenMapeo.manifiesto,
) -> MapeoCuenta:
    """Crea el mapeo de version origen a destino (unicidad por origen)."""
    existente = await db.scalar(
        select(MapeoCuenta).where(
            MapeoCuenta.empresa_id == empresa_id,
            MapeoCuenta.version_origen_id == version_origen_id,
            MapeoCuenta.version_destino_id == version_destino_id,
            MapeoCuenta.cuenta_origen_id == cuenta_origen_id,
        )
    )
    if existente is not None:
        raise CatalogoError(
            "mapeo_duplicado",
            "Ya existe un mapeo para esa cuenta origen entre estas versiones",
            422,
        )
    mapeo = MapeoCuenta(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        version_origen_id=version_origen_id,
        version_destino_id=version_destino_id,
        cuenta_origen_id=cuenta_origen_id,
        cuenta_destino_id=cuenta_destino_id,
        tipo_movimiento=tipo,
        requiere_reclasificacion=requiere_reclasificacion,
        origen=origen,
    )
    db.add(mapeo)
    await db.flush()
    return mapeo


async def _nueva_fila(
    db: AsyncSession,
    *,
    empresa_id: int,
    version: CatalogoVersion,
    cuenta: AccountPlan,
    proyeccion: dict[int, CatalogoCuenta],
    por_codigo: dict[str, CatalogoCuenta],
    estado: EstadoCuentaVersion,
    nombre: str,
) -> CatalogoCuenta:
    parent_row = (
        proyeccion.get(cuenta.parent_id) if cuenta.parent_id is not None else None
    )
    fila = CatalogoCuenta(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        version_id=version.id,
        account_id=cuenta.id,
        codigo_version=cuenta.code,
        nombre_version=nombre,
        estado=estado,
        parent_version_id=parent_row.id if parent_row is not None else None,
    )
    db.add(fila)
    proyeccion[cuenta.id] = fila
    por_codigo[cuenta.code] = fila
    await db.flush()
    return fila


async def aplicar_operaciones(
    db: AsyncSession,
    *,
    empresa_id: int,
    version: CatalogoVersion,
    base: CatalogoVersion | None,
    proyeccion: dict[int, CatalogoCuenta],
    plan: dict[str, AccountPlan],
    operaciones: list[dict[str, Any]],
    mapeo_explicito: list[dict[str, Any]],
) -> None:
    """Aplica altas, renombrados y bajas en ese orden (fases), luego el mapeo.

    - ``alta``: crea la cuenta en ``account_plan`` si falta y su fila nueva.
    - ``renombrado`` con destino distinto: origen pasa a ``renombrada`` y se
      enlaza con un ``MapeoCuenta`` manifiesto (crea el destino si falta).
    - ``renombrado`` de solo nombre: la fila sigue ``igual`` con el nombre
      nuevo y el mapeo apunta a la misma cuenta.
    - ``baja``: origen pasa a ``suprimida``; sin ``destino_codigo`` el mapeo
      queda sin destino y entra en ``pendientes_mapeo`` (FR-004).
    """
    por_codigo = {cc.codigo_version: cc for cc in proyeccion.values()}
    for op in operaciones:
        if op.get("operacion") not in ("alta", "renombrado", "baja"):
            raise CatalogoError(
                "operacion_invalida",
                f"Operacion desconocida: {op.get('operacion')!r}",
                422,
            )
    base_por_account: dict[int, CatalogoCuenta] = {}
    if base is not None:
        filas_base = (
            await db.scalars(
                select(CatalogoCuenta).where(
                    CatalogoCuenta.empresa_id == empresa_id,
                    CatalogoCuenta.version_id == base.id,
                )
            )
        ).all()
        base_por_account = {f.account_id: f for f in filas_base}
    elif any(op.get("operacion") in ("renombrado", "baja") for op in operaciones):
        raise CatalogoError(
            "operacion_sin_base",
            "No hay version base previa: renombrados y bajas exigen una version anterior",
            422,
        )

    for op in operaciones:
        if op.get("operacion") != "alta":
            continue
        codigo = validar_codigo(str(op.get("codigo") or ""))
        if codigo in por_codigo:
            raise CatalogoError(
                "codigo_duplicado", f"El codigo {codigo} ya existe en la version", 422
            )
        cuenta = await asegurar_cuenta_plan(
            db,
            empresa_id=empresa_id,
            codigo=codigo,
            nombre=str(op.get("nombre") or f"Cuenta {codigo}"),
            padre_codigo=op.get("padre_codigo"),
            plan=plan,
        )
        await _nueva_fila(
            db,
            empresa_id=empresa_id,
            version=version,
            cuenta=cuenta,
            proyeccion=proyeccion,
            por_codigo=por_codigo,
            estado=EstadoCuentaVersion.nueva,
            nombre=str(op.get("nombre") or f"Cuenta {codigo}"),
        )

    for op in operaciones:
        if op.get("operacion") != "renombrado":
            continue
        codigo = validar_codigo(str(op.get("codigo") or ""))
        origen = por_codigo.get(codigo)
        if origen is None or base is None:
            raise CatalogoError(
                "cuenta_no_encontrada",
                f"La cuenta {codigo} no existe en la version base",
                422,
            )
        nombre = op.get("nombre")
        destino_codigo = validar_codigo(
            str(op.get("destino_codigo") or codigo), "destino_codigo"
        )
        base_origen = base_por_account.get(origen.account_id)
        if base_origen is None:
            raise CatalogoError(
                "operacion_invalida",
                f"No se puede renombrar {codigo}: no tiene fila en la version base",
                422,
            )
        if destino_codigo == codigo:
            if nombre:
                origen.nombre_version = str(nombre)
            await crear_mapeo(
                db,
                empresa_id=empresa_id,
                version_origen_id=base.id,
                version_destino_id=version.id,
                cuenta_origen_id=base_origen.id,
                cuenta_destino_id=origen.id,
                tipo=TipoMovimiento.renombrada,
                requiere_reclasificacion=False,
            )
            continue
        destino = por_codigo.get(destino_codigo)
        if destino is None:
            cuenta_dest = await asegurar_cuenta_plan(
                db,
                empresa_id=empresa_id,
                codigo=destino_codigo,
                nombre=str(nombre or f"Cuenta {destino_codigo}"),
                padre_codigo=None,
                plan=plan,
            )
            destino = await _nueva_fila(
                db,
                empresa_id=empresa_id,
                version=version,
                cuenta=cuenta_dest,
                proyeccion=proyeccion,
                por_codigo=por_codigo,
                estado=EstadoCuentaVersion.nueva,
                nombre=str(nombre or f"Cuenta {destino_codigo}"),
            )
        origen.estado = EstadoCuentaVersion.renombrada
        await db.flush()
        await crear_mapeo(
            db,
            empresa_id=empresa_id,
            version_origen_id=base.id,
            version_destino_id=version.id,
            cuenta_origen_id=base_origen.id,
            cuenta_destino_id=destino.id,
            tipo=TipoMovimiento.renombrada,
            requiere_reclasificacion=True,
        )

    for op in operaciones:
        if op.get("operacion") != "baja":
            continue
        codigo = validar_codigo(str(op.get("codigo") or ""))
        origen = por_codigo.get(codigo)
        if origen is None or base is None:
            raise CatalogoError(
                "cuenta_no_encontrada",
                f"La cuenta {codigo} no existe en la version base",
                422,
            )
        if origen.estado == EstadoCuentaVersion.suprimida:
            raise CatalogoError(
                "operacion_duplicada", f"La cuenta {codigo} ya esta dada de baja", 422
            )
        base_origen = base_por_account.get(origen.account_id)
        if base_origen is None:
            raise CatalogoError(
                "operacion_invalida",
                f"No se puede dar de baja {codigo}: no tiene fila en la version base",
                422,
            )
        origen.estado = EstadoCuentaVersion.suprimida
        destino_baja: CatalogoCuenta | None = None
        destino_baja_codigo = op.get("destino_codigo")
        if destino_baja_codigo:
            destino_baja_codigo = validar_codigo(
                str(destino_baja_codigo), "destino_codigo"
            )
            if destino_baja_codigo != codigo:
                cuenta_dest = await asegurar_cuenta_plan(
                    db,
                    empresa_id=empresa_id,
                    codigo=destino_baja_codigo,
                    nombre=f"Cuenta {destino_baja_codigo}",
                    padre_codigo=None,
                    plan=plan,
                )
                destino_baja = por_codigo.get(destino_baja_codigo)
                if destino_baja is None:
                    destino_baja = await _nueva_fila(
                        db,
                        empresa_id=empresa_id,
                        version=version,
                        cuenta=cuenta_dest,
                        proyeccion=proyeccion,
                        por_codigo=por_codigo,
                        estado=EstadoCuentaVersion.nueva,
                        nombre=cuenta_dest.name,
                    )
            else:
                destino_baja = origen
        await db.flush()
        await crear_mapeo(
            db,
            empresa_id=empresa_id,
            version_origen_id=base.id,
            version_destino_id=version.id,
            cuenta_origen_id=base_origen.id,
            cuenta_destino_id=destino_baja.id if destino_baja is not None else None,
            tipo=TipoMovimiento.suprimida,
            requiere_reclasificacion=(
                destino_baja is None or destino_baja.account_id != origen.account_id
            ),
        )

    for par in mapeo_explicito:
        if base is None:
            raise CatalogoError(
                "operacion_sin_base",
                "El mapeo explicito exige una version base previa",
                422,
            )
        origen_codigo = validar_codigo(str(par.get("origen_codigo") or ""), "origen_codigo")
        destino_codigo = validar_codigo(
            str(par.get("destino_codigo") or ""), "destino_codigo"
        )
        origen = por_codigo.get(origen_codigo)
        if origen is None:
            raise CatalogoError(
                "cuenta_no_encontrada",
                f"La cuenta origen {origen_codigo} no existe en la version base",
                422,
            )
        base_origen = base_por_account.get(origen.account_id)
        if base_origen is None:
            raise CatalogoError(
                "operacion_invalida",
                f"La cuenta {origen_codigo} no tiene fila en la version base",
                422,
            )
        destino = por_codigo.get(destino_codigo)
        if destino is None:
            cuenta_dest = await asegurar_cuenta_plan(
                db,
                empresa_id=empresa_id,
                codigo=destino_codigo,
                nombre=f"Cuenta {destino_codigo}",
                padre_codigo=None,
                plan=plan,
            )
            destino = await _nueva_fila(
                db,
                empresa_id=empresa_id,
                version=version,
                cuenta=cuenta_dest,
                proyeccion=proyeccion,
                por_codigo=por_codigo,
                estado=EstadoCuentaVersion.nueva,
                nombre=cuenta_dest.name,
            )
        existente = await db.scalar(
            select(MapeoCuenta).where(
                MapeoCuenta.empresa_id == empresa_id,
                MapeoCuenta.version_origen_id == base.id,
                MapeoCuenta.version_destino_id == version.id,
                MapeoCuenta.cuenta_origen_id == base_origen.id,
            )
        )
        if existente is not None:
            if existente.cuenta_destino_id is not None:
                raise CatalogoError(
                    "mapeo_duplicado",
                    f"La cuenta {origen_codigo} ya tiene mapeo en esta version",
                    422,
                )
            existente.cuenta_destino_id = destino.id
            existente.requiere_reclasificacion = (
                destino.account_id != origen.account_id
            )
            if destino.account_id != origen.account_id:
                existente.tipo_movimiento = TipoMovimiento.renombrada
            await db.flush()
            continue
        await crear_mapeo(
            db,
            empresa_id=empresa_id,
            version_origen_id=base.id,
            version_destino_id=version.id,
            cuenta_origen_id=base_origen.id,
            cuenta_destino_id=destino.id,
            tipo=(
                TipoMovimiento.renombrada
                if destino.account_id != origen.account_id
                else TipoMovimiento.igual
            ),
            requiere_reclasificacion=destino.account_id != origen.account_id,
        )


async def mapeos_igualdad(
    db: AsyncSession,
    *,
    empresa_id: int,
    version: CatalogoVersion,
    base: CatalogoVersion | None,
    proyeccion: dict[int, CatalogoCuenta],
) -> int:
    """Autogenera ``MapeoCuenta`` ``igual`` para las cuentas sin cambio (FR-002)."""
    if base is None:
        return 0
    existentes = (
        await db.scalars(
            select(MapeoCuenta).where(
                MapeoCuenta.empresa_id == empresa_id,
                MapeoCuenta.version_origen_id == base.id,
                MapeoCuenta.version_destino_id == version.id,
            )
        )
    ).all()
    cubiertos = {m.cuenta_origen_id for m in existentes}
    creados = 0
    for cc in await _cuerpo_proyeccion(db, empresa_id, base):
        if cc.id in cubiertos:
            continue
        destino = proyeccion.get(cc.account_id)
        if destino is None:
            continue
        await crear_mapeo(
            db,
            empresa_id=empresa_id,
            version_origen_id=base.id,
            version_destino_id=version.id,
            cuenta_origen_id=cc.id,
            cuenta_destino_id=destino.id,
            tipo=TipoMovimiento.igual,
            requiere_reclasificacion=False,
            origen=OrigenMapeo.autogenerado,
        )
        creados += 1
    return creados


async def saldos_ejercicio(
    db: AsyncSession, empresa_id: int, ejercicio: int
) -> dict[int, Decimal]:
    """Neto POSTED (debe - haber) por cuenta del ejercicio (SC-003)."""
    filas = await db.execute(
        select(JournalEntryLine.account_id, func.sum(JournalEntryLine.debe - JournalEntryLine.haber))
        .join(
            JournalEntry,
            JournalEntry.id == JournalEntryLine.journal_entry_id,
        )
        .where(
            JournalEntryLine.empresa_id == empresa_id,
            JournalEntry.empresa_id == empresa_id,
            JournalEntry.estado == JournalEntryEstado.POSTED,
            JournalEntry.ejercicio == ejercicio,
            JournalEntryLine.account_id.is_not(None),
        )
        .group_by(JournalEntryLine.account_id)
    )
    return {int(account_id): Decimal(saldo) for account_id, saldo in filas.all() if saldo != 0}


async def saldo_total(db: AsyncSession, empresa_id: int, account_id: int) -> Decimal:
    """Neto POSTED historico de la cuenta (todos los ejercicios, FR-004)."""
    saldo = await db.scalar(
        select(func.coalesce(func.sum(JournalEntryLine.debe - JournalEntryLine.haber), 0))
        .join(
            JournalEntry,
            JournalEntry.id == JournalEntryLine.journal_entry_id,
        )
        .where(
            JournalEntryLine.empresa_id == empresa_id,
            JournalEntry.empresa_id == empresa_id,
            JournalEntry.estado == JournalEntryEstado.POSTED,
            JournalEntryLine.account_id == account_id,
        )
    )
    return Decimal(saldo or 0)


async def pendientes_mapeo(
    db: AsyncSession, empresa_id: int, version_id: uuid.UUID
) -> list[dict[str, str]]:
    """Mapeos sin destino con su motivo (``sin_destino``/``saldo_no_cero``)."""
    mapeos = (
        await db.scalars(
            select(MapeoCuenta).where(
                MapeoCuenta.empresa_id == empresa_id,
                MapeoCuenta.version_destino_id == version_id,
                MapeoCuenta.cuenta_destino_id.is_(None),
            )
        )
    ).all()
    items: list[dict[str, str]] = []
    for mapeo in mapeos:
        if mapeo.cuenta_origen_id is None:  # pragma: no cover - defensivo
            continue
        origen = await db.get(CatalogoCuenta, mapeo.cuenta_origen_id)
        if origen is None or origen.empresa_id != empresa_id:  # pragma: no cover
            continue
        saldo = await saldo_total(db, empresa_id, origen.account_id)
        items.append(
            {
                "codigo": origen.codigo_version,
                "motivo": "saldo_no_cero" if saldo != 0 else "sin_destino",
            }
        )
    items.sort(key=lambda i: i["codigo"])
    return items


async def contar_version(
    db: AsyncSession, empresa_id: int, version_id: uuid.UUID
) -> dict[str, int]:
    """Conteos del contrato de importacion (filas nuevas/suprimidas + manifiestos)."""
    filas = await db.execute(
        select(CatalogoCuenta.estado, func.count())
        .where(
            CatalogoCuenta.empresa_id == empresa_id,
            CatalogoCuenta.version_id == version_id,
        )
        .group_by(CatalogoCuenta.estado)
    )
    por_estado = {estado: int(n) for estado, n in filas.all()}
    mapeos_manifest = int(
        await db.scalar(
            select(func.count()).select_from(MapeoCuenta).where(
                MapeoCuenta.empresa_id == empresa_id,
                MapeoCuenta.version_destino_id == version_id,
                MapeoCuenta.origen == OrigenMapeo.manifiesto,
            )
        )
        or 0
    )
    renombradas = int(
        await db.scalar(
            select(func.count()).select_from(MapeoCuenta).where(
                MapeoCuenta.empresa_id == empresa_id,
                MapeoCuenta.version_destino_id == version_id,
                MapeoCuenta.origen == OrigenMapeo.manifiesto,
                MapeoCuenta.tipo_movimiento == TipoMovimiento.renombrada,
            )
        )
        or 0
    )
    return {
        "nuevas": por_estado.get(EstadoCuentaVersion.nueva, 0),
        "renombradas": renombradas,
        "suprimidas": por_estado.get(EstadoCuentaVersion.suprimida, 0),
        "mapeos": mapeos_manifest,
    }
