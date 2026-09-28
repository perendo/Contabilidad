"""Modulo de control presupuestario (SPEC-026).

- `presupuesto_service`: alta/actualizacion e importacion masiva (US1).
- `desviaciones`: cotejo presupuesto vs real del diario (US2).
- `informe_desviacion`: informe acumulado con totales y subtotales (US3).
- `cierre_periodo`: cierre con snapshot `Desviacion` inmutable (US3).
- `periodos`: periodos de seguimiento con numeracion correlativa (D8).
- `utils`: convencion de signos y cuantizacion decimal (D2/SC-005).
"""

from services.budget import (
    cierre_periodo,
    desviaciones,
    errores,
    informe_desviacion,
    periodos,
    presupuesto_service,
    utils,
)

__all__ = [
    "cierre_periodo",
    "desviaciones",
    "errores",
    "informe_desviacion",
    "periodos",
    "presupuesto_service",
    "utils",
]
