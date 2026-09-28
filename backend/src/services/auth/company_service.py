"""Company creation with PGC seed in the same transaction (SPEC-003 US4)."""

from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from models.iam.company import Company
from models.iam.user import User
from models.iam.user_company import UserCompany, UserRol
from services.acct.seed import seed_default_pgc
from services.audit.writer import audit_escribir
from services.security.catalogo import sembrar_seguridad


class CompanyError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def crear_empresa(
    db: AsyncSession,
    *,
    user_id: int,
    nif: str,
    razon_social: str,
    ip: str | None = None,
) -> tuple[Company, UserCompany]:
    """Insert company + ADMIN relation (new default) + seed PGC + security +
    audit.

    All inside the caller's ACID boundary (`flush` only): any failure —
    including the seed — rolls back the whole creation. The PG trigger
    `trg_companies_seed` / `trg_companies_rbac_seed` coexist safely: the seed
    is idempotent.
    """
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise CompanyError("usuario_invalido", "Usuario inexistente o inactivo")
    company = Company(nif=nif.strip(), razon_social=razon_social.strip())
    db.add(company)
    await db.flush()
    await db.execute(
        update(UserCompany)
        .where(UserCompany.user_id == user.id, UserCompany.is_default.is_(True))
        .values(is_default=False)
    )
    rel = UserCompany(
        user_id=user.id,
        company_id=company.company_id,
        role=UserRol.ADMIN,
        is_default=True,
    )
    db.add(rel)
    await db.flush()
    await seed_default_pgc(db, company.company_id)
    await sembrar_seguridad(db, empresa_id=company.company_id)
    await audit_escribir(
        db,
        empresa_id=company.company_id,
        actor=user.email,
        action="CREATE_COMPANY",
        entity="companies",
        entity_id=company.company_id,
        ip=ip,
    )
    await db.flush()
    return company, rel
