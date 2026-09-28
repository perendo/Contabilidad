"""Modulo de tesoreria: proyeccion de flujos, EFE y alertas de liquidez (SPEC-027).

Submodulos:
- `utils`: cuantizacion Decimal, buckets y formato de importes (puro).
- `clasificacion_actividad`: bloque operativa/inversion/financiacion (puro).
- `saldos`: lecturas de tesoreria del diario (SPEC-002) y conciliacion (SPEC-013).
- `proyeccion`: US1, generacion y refresh de la prevision.
- `efe`: US2, Estado de Flujos de Efectivo por cuenta y bloque.
- `alertas`: US3, deteccion y gestion de alertas de liquidez.
- `errores`: `CashflowError` con codigo estable y status HTTP.
"""

from __future__ import annotations

from services.cashflow.errores import CashflowError

__all__ = ["CashflowError"]
