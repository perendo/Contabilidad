"""Tests SPEC-003 Foundational (T011): unicidad y validez de modelos RBAC."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.iam.company import Company
from models.iam.user import User
from models.iam.user_company import UserCompany, UserRol
from services.auth.security import hash_password


async def _base(db: AsyncSession) -> tuple[int, int]:
    user = User(id=1, email="ana@x.es", password_hash=hash_password("pw"), full_name="Ana")
    db.add(user)
    company = Company(company_id=10, nif="A00000001", razon_social="Diez SL")
    db.add(company)
    await db.flush()
    return user.id, company.company_id


async def test_relacion_duplicada_rechazada(db_session: AsyncSession) -> None:
    user_id, company_id = await _base(db_session)
    db_session.add(
        UserCompany(id=1, user_id=user_id, company_id=company_id, role=UserRol.ADMIN)
    )
    await db_session.flush()
    db_session.add(
        UserCompany(id=2, user_id=user_id, company_id=company_id, role=UserRol.ACCOUNTANT)
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_defecto_unico_por_usuario(db_session: AsyncSession) -> None:
    user_id, _ = await _base(db_session)
    await crear_empresa(db_session, 20, nif="B00000002", razon_social="Veinte SL")
    await db_session.flush()
    db_session.add(
        UserCompany(
            id=1, user_id=user_id, company_id=10, role=UserRol.ADMIN, is_default=True
        )
    )
    await db_session.flush()
    db_session.add(
        UserCompany(
            id=2, user_id=user_id, company_id=20, role=UserRol.ADMIN, is_default=True
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_roles_validos_persisten(db_session: AsyncSession) -> None:
    user_id, _ = await _base(db_session)
    for cid, rol in (
        (20, UserRol.ADMIN),
        (30, UserRol.ACCOUNTANT),
        (40, UserRol.READ_ONLY),
    ):
        db_session.add(
            Company(company_id=cid, nif=f"N{cid:08d}", razon_social=f"E{cid} SL")
        )
    await db_session.flush()
    for rid, (cid, rol) in enumerate(
        (
            (20, UserRol.ADMIN),
            (30, UserRol.ACCOUNTANT),
            (40, UserRol.READ_ONLY),
        ),
        start=1,
    ):
        db_session.add(UserCompany(id=rid, user_id=user_id, company_id=cid, role=rol))
    await db_session.flush()
    rels = (
        await db_session.scalars(
            select(UserCompany).where(UserCompany.user_id == user_id)
        )
    ).all()
    assert {r.role for r in rels} == {UserRol.ADMIN, UserRol.ACCOUNTANT, UserRol.READ_ONLY}


async def test_email_unico(db_session: AsyncSession) -> None:
    await _base(db_session)
    db_session.add(
        User(id=2, email="ana@x.es", password_hash=hash_password("pw"), full_name="Otra")
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


# --------------------------------------------------------------------------
# SPEC-015 Foundational (T009): modelos de la matriz de permisos y auditoria.
# --------------------------------------------------------------------------

from models.rbac.evento_auditoria_acceso import (
    EventoAuditoriaAcceso,
    MotivoAcceso,
    ResultadoAcceso,
)
from models.rbac.matriz_permiso import MatrizPermiso
from models.rbac.permiso_operacion import (
    OperacionPermiso,
    PermisoOperacion,
)
from models.rbac.rol import Rol
from tests.conftest import crear_empresa


async def test_permiso_operacion_unico_por_modulo_operacion(
    db_session: AsyncSession,
) -> None:
    await _base(db_session)
    db_session.add(
        PermisoOperacion(
            modulo="acct",
            operacion=OperacionPermiso.ver,
            descripcion="duplicado",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_matriz_unica_por_empresa_rol_permiso(db_session: AsyncSession) -> None:
    await _base(db_session)
    rol = await db_session.scalar(
        select(Rol).where(Rol.empresa_id == 10, Rol.nombre == "READ_ONLY")
    )
    permiso = await db_session.scalar(
        select(PermisoOperacion).where(
            PermisoOperacion.modulo == "acct",
            PermisoOperacion.operacion == OperacionPermiso.ver,
        )
    )
    assert rol is not None and permiso is not None
    db_session.add(
        MatrizPermiso(empresa_id=10, rol_id=rol.id, permiso_id=permiso.id)
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_matriz_fk_compuesta_empresa_rol(db_session: AsyncSession) -> None:
    await _base(db_session)
    await crear_empresa(db_session, 20, nif="B00000002", razon_social="Veinte SL")
    await db_session.flush()
    rol_b = await db_session.scalar(
        select(Rol).where(Rol.empresa_id == 20, Rol.nombre == "ADMIN")
    )
    permiso = await db_session.scalar(
        select(PermisoOperacion).where(
            PermisoOperacion.modulo == "acct",
            PermisoOperacion.operacion == OperacionPermiso.ver,
        )
    )
    assert rol_b is not None and permiso is not None
    # empresa 10 + rol de la empresa 20 -> viola la FK compuesta (empresa_id, rol_id)
    db_session.add(
        MatrizPermiso(empresa_id=10, rol_id=rol_b.id, permiso_id=permiso.id)
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def _evento(db_session: AsyncSession) -> EventoAuditoriaAcceso:
    await _base(db_session)
    evento = EventoAuditoriaAcceso(
        empresa_id=10,
        usuario_id=1,
        modulo="acct",
        operacion="ver",
        resultado=ResultadoAcceso.deny,
        motivo=MotivoAcceso.sin_permiso,
    )
    db_session.add(evento)
    await db_session.flush()
    return evento


async def test_evento_auditoria_acceso_update_rechazado(db_session: AsyncSession) -> None:
    from sqlalchemy import update

    await _evento(db_session)
    with pytest.raises(IntegrityError):
        await db_session.execute(update(EventoAuditoriaAcceso).values(ip="1.2.3.4"))
        await db_session.flush()


async def test_evento_auditoria_acceso_delete_rechazado(db_session: AsyncSession) -> None:
    from sqlalchemy import delete

    evento = await _evento(db_session)
    with pytest.raises(IntegrityError):
        await db_session.execute(
            delete(EventoAuditoriaAcceso).where(EventoAuditoriaAcceso.id == evento.id)
        )
        await db_session.flush()
