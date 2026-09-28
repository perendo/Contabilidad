"""Account service (SPEC-001 US2+US3+US4): tenant-scoped selectable accounts, create, update."""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from services.audit.writer import audit_escribir


class SuggestError(ValueError):
    """Raised when an account suggestion query is invalid."""


class AccountError(ValueError):
    """Raised when an account operation fails."""

    def __init__(self, message: str, code: str = "account_error"):
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
            raise AccountError("nivel de la cuenta no coincide con el padre + 1", "level_mismatch")
        if not code.startswith(parent.code):
            raise AccountError("el código debe heredar el prefijo del padre", "code_prefix_mismatch")

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
        actor="user",  # Se sobrescribirá en el endpoint con el usuario real
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
        payload["name"] = {"old": cuenta.name, "new": name}
        cuenta.name = name

    if is_active is not None and is_active != cuenta.is_active:
        if is_active is False:
            # Desactivar: verificar protección (trigger DB lo hace, pero validamos antes para mensaje amigable)
            from models.acct.journal import JournalEntryLine

            used = await db.scalar(
                select(JournalEntryLine.id).where(
                    JournalEntryLine.account_id == cuenta.id,
                    JournalEntryLine.empresa_id == tenant_id,
                ).limit(1)
            )
            if used:
                raise AccountError(
                    "no se puede desactivar una cuenta con asientos asociados",
                    "account_has_entries",
                )
        payload["is_active"] = {"old": cuenta.is_active, "new": is_active}
        cuenta.is_active = is_active

    if not payload:
        return cuenta

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