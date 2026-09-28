"""Aggregate model imports.

Importing any submodule (e.g. `models.treasury`) runs this package first, so
every cross-spec table (iam, acct, ar, audit, treasury) is registered on
`Base.metadata` and composite FKs resolve during `create_all`.
"""

from models import (
    acct,
    ar,
    audit,
    budget,
    catalog,
    closing,
    costcenters,
    export,
    fiscal,
    iam,
    inmovilizado,
    invoice,
    monedas,
    navigation,
    ngo,
    rbac,
    reporting,
    templates,
    treasury,
)

__all__ = [
    "acct",
    "ar",
    "audit",
    "budget",
    "catalog",
    "closing",
    "costcenters",
    "export",
    "fiscal",
    "iam",
    "inmovilizado",
    "invoice",
    "monedas",
    "navigation",
    "ngo",
    "rbac",
    "reporting",
    "templates",
    "treasury",
]
