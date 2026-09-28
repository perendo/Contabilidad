"""AccountPlan model (SPEC-001). Aligned with the authoritative root plan.md DDL:
table `account_plan`, `tenant_id` naming, multi-tenant composite FKs."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class AccountPlan(Base):
    __tablename__ = "account_plan"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_account_plan_tenant_id"),
        UniqueConstraint("tenant_id", "code", name="uq_account_plan_tenant_code"),
        CheckConstraint("level BETWEEN 1 AND 5", name="account_plan_level_range"),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["companies.company_id"],
            name="fk_account_plan_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "parent_id"],
            ["account_plan.tenant_id", "account_plan.id"],
            name="fk_account_plan_parent",
        ),
        Index("ix_account_plan_tenant", "tenant_id"),
        Index("ix_account_plan_tenant_parent", "tenant_id", "parent_id"),
        Index("ix_account_plan_tenant_level", "tenant_id", "level", "is_selectable"),
        Index("ix_account_plan_tenant_code", "tenant_id", "code"),
        Index("ix_account_plan_name_trgm", "name"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    code: Mapped[str] = mapped_column(String(8), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_selectable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )