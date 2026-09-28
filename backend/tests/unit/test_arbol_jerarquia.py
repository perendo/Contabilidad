"""Tests SPEC-001 T011: jerarquía del árbol (FR-002, FR-005, FR-010)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.account_plan import AccountPlan
from models.iam.company import Company
from services.acct.plan_tree import build_tree
from services.acct.seed import seed_default_pgc


async def _crear_empresa(db: AsyncSession, tenant_id: int) -> Company:
    empresa = Company(company_id=tenant_id, nif=f"NIF-{tenant_id}", razon_social=f"Empresa {tenant_id}")
    db.add(empresa)
    await db.flush()
    return empresa


async def test_arbol_profundidad_hasta_5_niveles(db_session: AsyncSession) -> None:
    """El árbol soporta hasta 5 niveles de profundidad."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    # Crear cuenta nivel 5 manualmente bajo 1110
    padre_1110 = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "1110")
    )
    assert padre_1110 is not None

    cuenta_n5 = AccountPlan(
        tenant_id=1,
        code="11100001",
        level=5,
        name="Patrimonio neto - Socio A",
        parent_id=padre_1110.id,
        is_selectable=True,
    )
    db_session.add(cuenta_n5)
    await db_session.flush()

    arbol = await build_tree(db_session, 1)

    # Verificar que la cuenta nivel 5 aparece en el árbol
    def buscar_codigo(nodos: list[dict], code: str) -> dict | None:
        for n in nodos:
            if n["code"] == code:
                return n
            found = buscar_codigo(n["children"], code)
            if found:
                return found
        return None

    nodo_n5 = buscar_codigo(arbol, "11100001")
    assert nodo_n5 is not None
    assert nodo_n5["level"] == 5
    assert nodo_n5["is_selectable"] is True


async def test_arbol_nivel_equals_longitud_codigo(db_session: AsyncSession) -> None:
    """level == length(code) para niveles 1-4."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    arbol = await build_tree(db_session, 1)

    def verificar_niveles(nodos: list[dict]) -> None:
        for n in nodos:
            if n["level"] <= 4:
                assert len(n["code"]) == n["level"], f"code={n['code']}, level={n['level']}"
            verificar_niveles(n["children"])

    verificar_niveles(arbol)


async def test_arbol_orden_por_code(db_session: AsyncSession) -> None:
    """El árbol está ordenado por code."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    arbol = await build_tree(db_session, 1)

    def verificar_orden(nodos: list[dict]) -> None:
        codes = [n["code"] for n in nodos]
        assert codes == sorted(codes), f"No ordenado: {codes}"
        for n in nodos:
            verificar_orden(n["children"])

    verificar_orden(arbol)


async def test_is_selectable_solo_hojas_nivel_ge_4(db_session: AsyncSession) -> None:
    """Solo hojas (sin hijos) de nivel >= 4 son is_selectable=True."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    arbol = await build_tree(db_session, 1)

    def verificar_apuntabilidad(nodos: list[dict]) -> None:
        for n in nodos:
            tiene_hijos = len(n["children"]) > 0
            es_hoja = not tiene_hijos
            if es_hoja and n["level"] >= 4:
                assert n["is_selectable"] is True, f"Hoja nivel {n['level']} {n['code']} debería ser selectable"
            elif tiene_hijos:
                assert n["is_selectable"] is False, f"Cuenta con hijos {n['code']} no debería ser selectable"
            verificar_apuntabilidad(n["children"])

    verificar_apuntabilidad(arbol)


async def test_cuentas_inactivas_distinguibles(db_session: AsyncSession) -> None:
    """Cuentas inactivas se distinguen (is_active=False)."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    # Marcar una cuenta como inactiva
    cuenta = await db_session.scalar(
        select(AccountPlan).where(AccountPlan.tenant_id == 1, AccountPlan.code == "4300")
    )
    assert cuenta is not None
    cuenta.is_active = False
    await db_session.flush()

    arbol = await build_tree(db_session, 1)

    def buscar_inactiva(nodos: list[dict]) -> dict | None:
        for n in nodos:
            if n["code"] == "4300":
                return n
            found = buscar_inactiva(n["children"])
            if found:
                return found
        return None

    nodo_4300 = buscar_inactiva(arbol)
    assert nodo_4300 is not None
    assert nodo_4300["is_active"] is False


async def test_arbol_vacio_sin_error(db_session: AsyncSession) -> None:
    """Plan vacío devuelve lista vacía sin error."""
    await _crear_empresa(db_session, 1)
    # No hacer seed

    arbol = await build_tree(db_session, 1)
    assert arbol == []


async def test_arbol_incluye_parent_id(db_session: AsyncSession) -> None:
    """Cada nodo incluye parent_id para navegación frontend."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    arbol = await build_tree(db_session, 1)

    def verificar_parent_id(nodos: list[dict]) -> None:
        for n in nodos:
            assert "parent_id" in n
            if n["parent_id"] is not None:
                assert isinstance(n["parent_id"], int)
            verificar_parent_id(n["children"])

    verificar_parent_id(arbol)


async def test_arbol_estructura_completa(db_session: AsyncSession) -> None:
    """Estructura completa: raiz -> subgrupos -> cuentas -> subcuentas."""
    await _crear_empresa(db_session, 1)
    await seed_default_pgc(db_session, 1)

    arbol = await build_tree(db_session, 1)

    # Debe haber 7 raíces (grupos 1-7)
    assert len(arbol) == 7
    raiz_codes = {n["code"] for n in arbol}
    assert raiz_codes == {"1", "2", "3", "4", "5", "6", "7"}

    # Cada grupo tiene subgrupos (nivel 2)
    for grupo in arbol:
        assert grupo["level"] == 1
        assert len(grupo["children"]) > 0
        for subgrupo in grupo["children"]:
            assert subgrupo["level"] == 2
            assert subgrupo["code"].startswith(grupo["code"])