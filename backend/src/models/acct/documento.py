"""Documento adjunto a un asiento del diario (SPEC-030 T006).

Evidencia documental: un PDF o una imagen (JPEG, PNG, TIFF) anclada a un
asiento, con huella SHA-256 del contenido y alta trazada.

Inmutabilidad (constitucion II, research D3): el contenido, su nombre y su
huella **nunca** se reescriben. El cambio esta bloqueado a nivel de base de
datos por `trg_documento_asiento_contenido_inmutable_update` y el borrado fisico
por `trg_documento_asiento_inmutable_delete` (espejo SQLite en `db/triggers.py`).
Lo unico que se puede modificar son las cuatro columnas de la baja logica
(`estado`, `baja_motivo`, `baja_usuario`, `baja_at`), porque FR-012 exige que la
baja no suprima el soporte contable durante el plazo legal de conservacion y
FR-010 la restringe a asientos en borrador. La correccion de una evidencia
incorrecta se hace dando de baja y volver a adjuntar, nunca sobreescribiendo.

Multi-tenancy (constitucion III): `empresa_id` en la clave unica que consume la
FK compuesta, en los cuatro indices y en el filtro de toda consulta. La FK
`(empresa_id, journal_entry_id) -> journal_entry (empresa_id, id)` impide en la
base de datos que un documento de una empresa se ancle a un asiento de otra,
aunque la aplicacion fallara (data-model.md seccion 7.5).

Duplicados (FR-006, research D6): `UNIQUE (empresa_id, journal_entry_id, sha256)`
**sin** indice parcial, porque la baja es logica y la huella sigue ocupando su
sitio: permitir re-adjuntar tras una baja rompe la unicidad del rastro. El mismo
fichero si puede ir a asientos distintos.

Opcionalidad (FR-020, research D11): esta tabla no impose nada al diario. No hay
recuento en `journal_entry`, ni `NOT NULL`, ni `CHECK` que la referencie, y
ningun flujo contable, fiscal o de cierre consulta su existencia. Un asiento
puede no tener nunca un solo documento.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from base import Base

#: Longitudes de los campos de texto (research D18). Se validan tambien en
#: `services/documentos/validacion.py` antes de insertar, para devolver
#: `documento_nombre_largo` en vez de un error de integridad de la BD.
NOMBRE_MAX: int = 255
DESCRIPCION_MAX: int = 500
BAJA_MOTIVO_MAX: int = 500


class TipoDocumento(str, Enum):
    """Lista cerrada de clasificacion (research D17).

    El cliente no puede introducir valores fuera del conjunto: un valor
    desconocido produce `tipo_documento_invalido` (422). Se aniadio `contrato`
    porque un apunte de arrendamiento o de prestacion de servicios se documenta
    con un contrato, no con un recibo; sin el, el filtro por tipo (FR-017) seria
    poco fiable.
    """

    factura = "factura"
    recibo = "recibo"
    extracto = "extracto"
    justificante = "justificante"
    contrato = "contrato"
    otro = "otro"


class EstadoDocumento(str, Enum):
    """`activo` visible y descargable; `dado_de_baja` baja logica (FR-012).

    Transicion unica e irreversible: no hay endpoint de borrado fisico y el
    trigger `BEFORE DELETE` lo rechazaria.
    """

    activo = "activo"
    dado_de_baja = "dado_de_baja"


#: Columnas que el trigger de inmutabilidad considera congeladas: cualquiera de
#: ellas distinta en el `UPDATE` aborta la sentencia. Las columnas de la baja
#: quedan fuera a proposito (research D3).
COLUMNAS_INMUTABLES: tuple[str, ...] = (
    "empresa_id",
    "journal_entry_id",
    "contenido",
    "sha256",
    "nombre_original",
    "content_type",
    "extension",
    "size_bytes",
    "num_paginas",
    "tipo_documento",
    "descripcion",
    "importe_informativo",
    "created_by",
    "created_at",
)


class DocumentoAsiento(Base):
    """Fichero de evidencia anclado a un asiento del diario."""

    __tablename__ = "documento_asiento"
    __table_args__ = (
        # Clave tenant que consume la FK compuesta (constitucion III).
        UniqueConstraint("empresa_id", "id", name="uq_documento_asiento_empresa_id"),
        # FR-006 / research D6: el mismo fichero no se adjunta dos veces al
        # mismo asiento, y la unicidad sigue vigente tras una baja logica.
        UniqueConstraint(
            "empresa_id",
            "journal_entry_id",
            "sha256",
            name="uq_documento_asiento_huella",
        ),
        # Aislamiento cross-tenant a nivel de base de datos: un documento de la
        # empresa A no puede colgar de un asiento de la empresa B.
        ForeignKeyConstraint(
            ["empresa_id", "journal_entry_id"],
            ["journal_entry.empresa_id", "journal_entry.id"],
            name="fk_documento_asiento_entrada",
        ),
        CheckConstraint("size_bytes > 0", name="chk_documento_asiento_tamano"),
        # Una baja siempre esta completa y trazada (FR-011, FR-012).
        CheckConstraint(
            "(estado = 'activo' AND baja_motivo IS NULL AND baja_usuario IS NULL"
            " AND baja_at IS NULL)"
            " OR (estado = 'dado_de_baja' AND baja_motivo IS NOT NULL"
            " AND baja_usuario IS NOT NULL AND baja_at IS NOT NULL)",
            name="chk_documento_asiento_baja",
        ),
        # research D19: el importe es solo referencia visual; sin negativos.
        CheckConstraint(
            "importe_informativo IS NULL OR importe_informativo >= 0",
            name="chk_documento_asiento_importe",
        ),
        # Filtro de tenant en toda consulta (constitucion III).
        Index("ix_documento_asiento_empresa_id", "empresa_id"),
        # Listado del asiento en orden determinista (research D15).
        Index(
            "ix_documento_asiento_entrada",
            "empresa_id",
            "journal_entry_id",
            "created_at",
            "id",
        ),
        # Listado global por ejercicio (FR-017); el ejercicio es del asiento, asi
        # que se resuelve con JOIN en `services/documentos/consulta.py`.
        Index("ix_documento_asiento_ejercicio", "empresa_id", "created_at"),
        Index("ix_documento_asiento_tipo", "empresa_id", "tipo_documento"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # `empresa_id` **no** lleva `index=True`: el indice con nombre esta
    # declarado en `__table_args__` (`ix_documento_asiento_empresa_id`), y
    # duplicarlo hace fallar `create_all` con "index already exists".
    empresa_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    journal_entry_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    contenido: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    nombre_original: Mapped[str] = mapped_column(String(NOMBRE_MAX), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    extension: Mapped[str] = mapped_column(String(10), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    num_paginas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tipo_documento: Mapped[TipoDocumento] = mapped_column(
        SqlEnum(
            TipoDocumento,
            name="documento_tipo",
            values_callable=lambda enum: [m.value for m in enum],
        ),
        nullable=False,
    )
    descripcion: Mapped[str | None] = mapped_column(
        String(DESCRIPCION_MAX), nullable=True
    )
    #: Referencia visual con 4 decimales; nunca se suma ni traslada al asiento
    #: (constitucion: prohibido `float` para importes).
    importe_informativo: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    estado: Mapped[EstadoDocumento] = mapped_column(
        SqlEnum(
            EstadoDocumento,
            name="documento_estado",
            values_callable=lambda enum: [m.value for m in enum],
        ),
        nullable=False,
        default=EstadoDocumento.activo,
        server_default=text("'activo'"),
    )
    baja_motivo: Mapped[str | None] = mapped_column(
        String(BAJA_MOTIVO_MAX), nullable=True
    )
    baja_usuario: Mapped[str | None] = mapped_column(String(120), nullable=True)
    baja_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    @property
    def dado_de_baja(self) -> bool:
        return self.estado == EstadoDocumento.dado_de_baja
