"""Tests SPEC-001 T024: rechazos en alta de cuenta (US3)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.iam.company import Company
from services.acct.account_service import AccountError, crear_cuenta
from services.acct.seed import seed_default_pgc


async def _crear_empresa(db: AsyncSession, tenant_id: int) -> Company:
    empresa = Company(company_id=tenant_id, nif=f"NIF-{tenant_id}", razon_social=f"Empresa {tenant_id}")
    db.add(empresa)
    await db.flush()
    return empresa


async def test_alta_codigo_duplicado_rechazado_409(db_session: AsyncSession) -> None:
    """Código duplicado en misma empresa → AccountError code_duplicate."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    # 4300 ya existe
    with pytest.raises(AccountError) as exc:
        await crear_cuenta(db_session, 1, "4300", "Duplicado", None)
    assert exc.value.code == "code_duplicate"


async def test_alta_nivel5_con_hija_rechazado_422(db_session: AsyncSession) -> None:
    """Nivel 5 no puede tener hijas → cualquier código hijo excede 8 dígitos (code_too_long)."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    # Crear nivel 5 (código 8 dígitos, válido)
    padre_n4 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    nivel5 = await crear_cuenta(db_session, 1, "43000001", "Nivel 5", padre_n4.id)
    assert nivel5.level == 5

    # Intentar crear hija bajo nivel 5: cualquier código válido necesitaría 9+ dígitos
    # El servicio rechaza por code_too_long antes de validar parent_level_max
    with pytest.raises(AccountError) as exc:
        await crear_cuenta(db_session, 1, "430000011", "Hija de nivel 5", nivel5.id)
    # La validación de longitud de código ocurre primero
    assert exc.value.code == "code_too_long"


async def test_alta_codigo_no_numerico_rechazado_422(db_session: AsyncSession) -> None:
    """Código con letras → AccountError code_not_numeric."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    with pytest.raises(AccountError) as exc:
        await crear_cuenta(db_session, 1, "430A", "Inválido", None)
    assert exc.value.code == "code_not_numeric"


async def test_alta_nivel_longitud_inconsistente_rechazado_422(db_session: AsyncSession) -> None:
    """Nivel no coincide con longitud del código (1-4) → AccountError level_mismatch."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    # Código 3 dígitos pero intentando crear como nivel 4 (padre nivel 3)
    padre_n3 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "430")
    )
    with pytest.raises(AccountError) as exc:
        await crear_cuenta(db_session, 1, "430", "Inconsistente", padre_n3.id)
    assert exc.value.code == "level_mismatch"


async def test_alta_codigo_demasiado_largo_rechazado_422(db_session: AsyncSession) -> None:
    """Código > 8 dígitos → AccountError code_too_long."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    with pytest.raises(AccountError) as exc:
        await crear_cuenta(db_session, 1, "123456789", "Demasiado largo", None)
    assert exc.value.code == "code_too_long"


async def test_alta_nivel_maximo_superado_rechazado_422(db_session: AsyncSession) -> None:
    """Intentar crear nivel 6 → AccountError level_max."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    # Código de 9 dígitos implicaría nivel 6 (no permitido)
    with pytest.raises(AccountError) as exc:
        await crear_cuenta(db_session, 1, "123456789", "Nivel 6", None)
    assert exc.value.code in ("code_too_long", "level_max")


async def test_alta_padre_inexistente_rechazado_404(db_session: AsyncSession) -> None:
    """Padre inexistente → AccountError parent_not_found."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    with pytest.raises(AccountError) as exc:
        await crear_cuenta(db_session, 1, "4301", "Sin padre", 999999)
    assert exc.value.code == "parent_not_found"


async def test_alta_padre_inactivo_rechazado_404(db_session: AsyncSession) -> None:
    """Padre inactivo → AccountError parent_inactive."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    padre = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    assert padre is not None
    padre.is_active = False
    await db_session.flush()

    with pytest.raises(AccountError) as exc:
        await crear_cuenta(db_session, 1, "43000001", "Hija", padre.id)
    assert exc.value.code == "parent_inactive"


async def test_alta_prefijo_codigo_no_hereda_padre_rechazado_422(db_session: AsyncSession) -> None:
    """Código no hereda prefijo del padre → AccountError code_prefix_mismatch."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    padre = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    assert padre is not None

    # 5700 no empieza por 4300
    with pytest.raises(AccountError) as exc:
        await crear_cuenta(db_session, 1, "57000001", "Prefijo malo", padre.id)
    assert exc.value.code == "code_prefix_mismatch"


async def test_alta_nivel_salto_mas_de_uno_rechazado_422(db_session: AsyncSession) -> None:
    """Saltarse niveles (padre nivel 2, hija nivel 4) → level_mismatch."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    # Padre nivel 2 (ej. 11)
    padre_n2 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "11")
    )
    assert padre_n2 is not None and padre_n2.level == 2

    # Intentar crear nivel 4 directamente (debería ser nivel 3)
    with pytest.raises(AccountError) as exc:
        await crear_cuenta(db_session, 1, "1118", "Salto nivel", padre_n2.id)
    assert exc.value.code == "level_mismatch"