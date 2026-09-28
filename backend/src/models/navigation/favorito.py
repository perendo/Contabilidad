"""Favorito de navegacion (SPEC-031).

Vincula un usuario, una empresa y un destino, con su posicion en el orden que eligio
el usuario. Es la unica entidad que añade esta feature.

`destino` es la **clave** del mapa de superficies y no una ruta, y esa distincion es
lo que hace cumplir FR-026: reubicar una opcion cambia `ruta` y deja `clave`
intacta, de modo que los favoritos siguen resolviendo sin migrar nada.

La FK compuesta a `user_companies` hace la garantia de constitution III en la base y
no en el servicio: un favorito de una empresa a la que el usuario no esta vinculado es
**invalido**, no invisible. Sin ella, el aislamiento dependeria de que cada consulta
se acuerde del filtro.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base


class FavoritoUsuario(Base):
    __tablename__ = "favorito_usuario"
    __table_args__ = (
        # Convencion de las 30 specs previas: clave unica por tenant, que es lo que
        # permite FKs compuestas hacia esta tabla.
        UniqueConstraint("empresa_id", "id", name="uq_favorito_usuario_tenant_id"),
        # Un destino no se marca dos veces. Sin este indice, dos marcas desde dos
        # pestanas crean duplicados y el panel los muestra dos veces.
        UniqueConstraint(
            "empresa_id", "usuario_id", "destino", name="uq_favorito_usuario_destino"
        ),
        CheckConstraint('"orden" >= 1', name="ck_favorito_usuario_orden"),
        # Sin esto, la cadena vacia colisionaria en el UNIQUE y todos los favoritos
        # sin destino se fundirian en uno.
        CheckConstraint("length(destino) > 0", name="ck_favorito_usuario_destino_no_vacio"),
        # constitution III a nivel de esquema: el favorito solo existe si el usuario
        # esta vinculado a esa empresa.
        #
        # El orden de las columnas es `(usuario_id, empresa_id)` porque es el del UNIQUE
        # `uq_user_companies_pair (user_id, company_id)`. Aqui la columna de empresa
        # se llama `empresa_id` y la de `user_companies` se llama `company_id`: son
        # el mismo tenant con dos nombres, y por eso la FK las empareja de forma
        # cruzada. Poner `(empresa_id, usuario_id)` no resolveria, porque no hay
        # ningun indice unico en ese orden.
        ForeignKeyConstraint(
            ["usuario_id", "empresa_id"],
            ["user_companies.user_id", "user_companies.company_id"],
            name="fk_favorito_usuario_vinculo",
        ),
        Index("ix_favorito_usuario_orden", "empresa_id", "usuario_id", "orden"),
        Index("ix_favorito_usuario_destino", "empresa_id", "destino"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    usuario_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    #: Clave del mapa de superficies. Estable aunque la ruta se reubique (FR-026).
    destino: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Posicion elegida por el usuario. Puede pasar de 5: el limite es de LECTURA.
    orden: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
