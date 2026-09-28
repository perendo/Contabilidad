"""Company entity (SPEC-003). Top-level multi-tenant anchor referenced by
account_plan.tenant_id and user_companies.company_id."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class Company(Base):
    __tablename__ = "companies"

    company_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True
    )
    nif: Mapped[str] = mapped_column(String(20), nullable=False)
    razon_social: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )