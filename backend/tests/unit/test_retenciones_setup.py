from __future__ import annotations

from api.deps import get_empresa_id
from api.fiscal.deps import get_empresa_id as fiscal_get_empresa_id
from api.fiscal.routes_retenciones import router


def test_deps_fiscal_reutiliza_dependencia_compartida() -> None:
    assert fiscal_get_empresa_id is get_empresa_id


def test_router_retenciones_usa_prefijo_y_sesion() -> None:
    assert router.prefix == "/api/v1/fiscal/retenciones"
    assert any(
        dependency.dependency is get_empresa_id
        for dependency in router.dependencies
    )
