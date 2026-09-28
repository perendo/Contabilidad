"""SerieFactura model (SPEC-007 T006): serie de numeracion configurable.

Multi-tenant (constitución III): ``empresa_id`` forma parte de la clave de
unicidad y de todos los índices. La numeración avanza correlativamente por
``(empresa_id, serie_id, ejercicio)`` sin reutilizar números anulados
(constitución IV); ``siguiente_numero`` es el contador global de la serie y el
número real de cada ejercicio se deriva de las facturas ya emitidas.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    BigInteger,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class SerieFacturaEstado(str, enum.Enum):
    activa = "activa"
    inactiva = "inactiva"


class SerieFactura(Base):
    __tablename__ = "serie_factura"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_serie_factura_tenant_id"),
        UniqueConstraint(
            "empresa_id", "codigo", name="uq_serie_factura_tenant_codigo"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    codigo: Mapped[str] = mapped_column(String(10), nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    prefijo: Mapped[str] = mapped_column(String(10), nullable=False)
    sufijo: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    siguiente_numero: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    estado: Mapped[SerieFacturaEstado] = mapped_column(
        SqlEnum(SerieFacturaEstado, name="serie_factura_estado"),
        nullable=False,
        default=SerieFacturaEstado.activa,
    )