"""User-Company relationship with role (SPEC-003). One active role per pair,
one default company per user (partial unique index)."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class UserRol(str, enum.Enum):
    ADMIN = "ADMIN"
    ACCOUNTANT = "ACCOUNTANT"
    READ_ONLY = "READ_ONLY"


class UserCompany(Base):
    __tablename__ = "user_companies"
    __table_args__ = (
        UniqueConstraint("user_id", "company_id", name="uq_user_companies_pair"),
        Index(
            "uq_user_companies_default_one",
            "user_id",
            unique=True,
            sqlite_where=text("is_default = 1"),
            postgresql_where=text("is_default = TRUE"),
        ),
        ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_user_companies_user"
        ),
        ForeignKeyConstraint(
            ["company_id"], ["companies.company_id"], name="fk_user_companies_company"
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    company_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    role: Mapped[UserRol] = mapped_column(
        SqlEnum(UserRol, name="user_company_rol"), nullable=False
    )
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )