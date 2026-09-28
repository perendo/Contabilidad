"""Structural tests for the treasury module scaffold (T001, T003)."""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = REPO_ROOT / "backend" / "src"

BACKEND_MODULES = [
    "models/treasury/__init__.py",
    "services/remittance/__init__.py",
    "services/discount.py",
    "services/remittance/sepa_dd.py",
    "services/remittance/csb_1919.py",
    "services/remittance/refund_r19.py",
    "api/treasury/__init__.py",
    "api/treasury/routes.py",
    "api/treasury/deps.py",
]

IMPORTABLE_MODULES = [
    "models.treasury",
    "services.remittance",
    "services.discount",
    "services.remittance.sepa_dd",
    "services.remittance.csb_1919",
    "services.remittance.refund_r19",
    "api.treasury",
    "api.treasury.routes",
    "api.treasury.deps",
]

FRONTEND_DIRS = [
    "frontend/src/app/remesas",
    "frontend/src/app/devoluciones",
    "frontend/src/app/terceros/condiciones",
    "frontend/src/components/treasury",
]


@pytest.mark.parametrize("relative_path", BACKEND_MODULES)
def test_backend_module_file_exists(relative_path):
    assert (BACKEND_SRC / relative_path).is_file()


@pytest.mark.parametrize("module_name", IMPORTABLE_MODULES)
def test_backend_module_is_importable(module_name):
    __import__(module_name)


@pytest.mark.parametrize("relative_dir", FRONTEND_DIRS)
def test_frontend_directory_exists(relative_dir):
    assert (REPO_ROOT / relative_dir).is_dir()
