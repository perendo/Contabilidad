"""Account plan service: business logic for tree, suggest, and CRUD."""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from services.audit.writer import audit_escribir


class SuggestError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = "suggest_error"


class AccountError(Exception):
    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


async def suggest(
    db: AsyncSession,
    tenant_id: int,
    q: str,
    *,
    limit: int = 50,
) -> list[dict]:
    """Suggest active, selectable accounts by code prefix or name fragment."""
    query = q.strip()
    if not query:
        raise SuggestError("la consulta no puede estar vacía")
    if limit <= 0:
        raise SuggestError("limit debe ser mayor que cero")

    cuentas = (
        await db.scalars(
            select(AccountPlan)
            .where(
                AccountPlan.tenant_id == tenant_id,
                AccountPlan.is_selectable.is_(True),
                AccountPlan.is_active.is_(True),
                or_(
                    AccountPlan.code.startswith(query),
                    AccountPlan.name.ilike(f"%{query}%"),
                ),
            )
            .order_by(AccountPlan.code)
            .limit(limit)
        )
    ).all()

    return [
        {
            "id": cuenta.id,
            "tenant_id": cuenta.tenant_id,
            "code": cuenta.code,
            "name": cuenta.name,
            "level": cuenta.level,
            "is_selectable": cuenta.is_selectable,
            "is_active": cuenta.is_active,
        }
        for cuenta in cuentas
    ]


async def crear_cuenta(
    db: AsyncSession,
    tenant_id: int,
    code: str,
    name: str,
    parent_id: int | None = None,
) -> AccountPlan:
    """Create a new account/subaccount with validation."""
    # Validar código numérico
    if not code.isdigit():
        raise AccountError("el código debe ser numérico", "code_not_numeric")

    # Validar longitud según nivel
    if len(code) <= 4:
        expected_level = len(code)
    elif 5 <= len(code) <= 8:
        expected_level = 5
    else:
        raise AccountError("código demasiado largo (máx 8 dígitos)", "code_too_long")

    # Autodeducción del padre si no se especifica y el nivel > 1
    if parent_id is None and expected_level > 1:
        # Longitudes candidatas de la cuenta padre en orden decreciente
        prefijos = []
        if expected_level == 5:
            # Para nivel 5, el padre debe ser nivel 4 (4 dígitos)
            prefijos = [code[:4]]
        elif expected_level == 4:
            # Para nivel 4, el padre debe ser nivel 3 (3 dígitos)
            prefijos = [code[:3]]
        elif expected_level == 3:
            # Para nivel 3, el padre debe ser nivel 2 (2 dígitos)
            prefijos = [code[:2]]
        elif expected_level == 2:
            # Para nivel 2, el padre debe ser nivel 1 (1 dígito)
            prefijos = [code[:1]]

        for pref in prefijos:
            padre_candidato = await db.scalar(
                select(AccountPlan).where(
                    AccountPlan.tenant_id == tenant_id,
                    AccountPlan.code == pref,
                    AccountPlan.level == expected_level - 1,
                    AccountPlan.is_active.is_(True),
                )
            )
            if padre_candidato is not None:
                parent_id = padre_candidato.id
                break

        if parent_id is None:
            # Determinar código esperado del padre para informar con exactitud
            padre_sug = prefijos[0] if prefijos else ""
            raise AccountError(
                f"No se encontró la cuenta padre activa '{padre_sug}' (nivel {expected_level - 1}) para crear '{code}'. Debes dar de alta primero la cuenta '{padre_sug}'.",
                "parent_required",
            )

    # Validar padre si se proporciona
    parent = None
    if parent_id is not None:
        parent = await db.get(AccountPlan, parent_id)
        if parent is None or parent.tenant_id != tenant_id:
            raise AccountError("cuenta padre inexistente en la empresa activa", "parent_not_found")
        if not parent.is_active:
            raise AccountError("la cuenta padre debe estar activa", "parent_inactive")
        if parent.level >= 5:
            raise AccountError("no se puede crear hija de una cuenta de nivel 5", "parent_level_max")
        if parent.level + 1 != expected_level:
            raise AccountError(
                f"Nivel de la cuenta ({expected_level}) no coincide con el padre + 1 (nivel del padre '{parent.code}': {parent.level}).",
                "level_mismatch",
            )
        if not code.startswith(parent.code):
            raise AccountError(
                f"El código '{code}' debe heredar el prefijo del padre '{parent.code}'.",
                "code_prefix_mismatch",
            )

    # Verificar nivel máximo
    if expected_level > 5:
        raise AccountError("profundidad máxima superada (5 niveles)", "level_max")

    # Verificar si ya existe una cuenta con ese código en el tenant
    existing = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == tenant_id, AccountPlan.code == code
        )
    )
    if existing:
        raise AccountError("código ya existente en la empresa", "code_duplicate")

    # Crear la cuenta
    cuenta = AccountPlan(
        tenant_id=tenant_id,
        code=code,
        name=name,
        parent_id=parent_id,
        level=expected_level,
        is_selectable=(expected_level >= 4 and parent_id is not None),  # hoja nivel >= 4
    )
    db.add(cuenta)
    await db.flush()

    # Auditoría
    await audit_escribir(
        db,
        empresa_id=tenant_id,
        actor="user",
        action="CREATE",
        entity="account_plan",
        entity_id=cuenta.id,
        payload={
            "code": code,
            "name": name,
            "level": expected_level,
            "parent_id": parent_id,
        },
    )

    return cuenta


async def actualizar_cuenta(
    db: AsyncSession,
    tenant_id: int,
    account_id: int,
    *,
    name: str | None = None,
    is_active: bool | None = None,
) -> AccountPlan:
    """Update account name and/or active status with protection checks."""
    cuenta = await db.scalar(
        select(AccountPlan).where(
            AccountPlan.tenant_id == tenant_id, AccountPlan.id == account_id
        )
    )
    if cuenta is None:
        raise AccountError("cuenta inexistente en la empresa activa", "not_found")

    payload: dict = {}

    if name is not None and name != cuenta.name:
        # Verificar unicidad del nombre
        existing = await db.scalar(
            select(AccountPlan).where(
                AccountPlan.tenant_id == tenant_id,
                AccountPlan.name == name,
                AccountPlan.id != account_id,
            )
        )
        if existing:
            raise AccountError("nombre ya existente en la empresa", "name_duplicate")
        payload["name_anterior"] = cuenta.name
        payload["name_nuevo"] = name
        cuenta.name = name

    if is_active is not None and is_active != cuenta.is_active:
        payload["is_active_anterior"] = cuenta.is_active
        payload["is_active_nuevo"] = is_active
        cuenta.is_active = is_active

    await db.flush()

    # Auditoría
    await audit_escribir(
        db,
        empresa_id=tenant_id,
        actor="user",
        action="UPDATE",
        entity="account_plan",
        entity_id=cuenta.id,
        payload=payload,
    )

    return cuenta
