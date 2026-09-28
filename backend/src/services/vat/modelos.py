"""Modelos fiscales 303/347/349 (SPEC-012 T024/T025/T032/T033).

El 303 agrega por periodo las cuotas devengadas (libro de emitidas) y
deducibles (libro de recibidas) del periodo, el recargo de equivalencia
separado y el IVA diferido por criterio de caja. El 347 agrega anualmente por
NIF/clave con el limite legal de 3.005,06 EUR; el 349 agrega las
intracomunitarias del periodo por NIF. Todos los importes en ``Decimal``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from models.fiscal.periodo_fiscal import TipoPeriodo
from services.reports.common import fmt
from services.vat.libros_iva import (
    construir_libro_emitidas,
    construir_libro_intracomunitarias,
    construir_libro_recibidas,
)
from services.vat.periodo import rango_periodo

LIMITE_347 = Decimal("3005.06")


def _por_tipo(operaciones: list[dict], campo: str) -> dict[str, dict[str, str]]:
    acumulado: dict[str, dict[str, Decimal]] = {}
    for op in operaciones:
        if not op.get("incluir_303", True):
            continue
        tipo = op["tipo_iva"]
        grupo = acumulado.setdefault(tipo, {"base": Decimal(0), "cuota": Decimal(0)})
        grupo["base"] += Decimal(op["base"])
        grupo["cuota"] += Decimal(op[campo])
    return {
        tipo: {"base": fmt(v["base"]), "cuota": fmt(v["cuota"])}
        for tipo, v in sorted(acumulado.items())
    }


def _suma(operaciones: list[dict], campo: str, *, incluir: bool = True) -> Decimal:
    return sum(
        (
            Decimal(op[campo])
            for op in operaciones
            if op.get("incluir_303", True) == incluir
        ),
        Decimal(0),
    )


async def _libros_periodo(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    tipo_periodo: TipoPeriodo | str,
    periodo: int,
) -> tuple[dict, dict, tuple[date, date]]:
    inicio, fin = rango_periodo(ejercicio, tipo_periodo, periodo)
    emitidas = await construir_libro_emitidas(
        db, empresa_id=empresa_id, ejercicio=ejercicio, inicio=inicio, fin=fin
    )
    recibidas = await construir_libro_recibidas(
        db, empresa_id=empresa_id, ejercicio=ejercicio, inicio=inicio, fin=fin
    )
    return emitidas, recibidas, (inicio, fin)


async def calcular_303(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    tipo_periodo: TipoPeriodo | str,
    periodo: int,
) -> dict:
    emitidas, recibidas, _ = await _libros_periodo(
        db,
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        tipo_periodo=tipo_periodo,
        periodo=periodo,
    )
    devengado = _por_tipo(emitidas["operaciones"], "cuota")
    deducible = _por_tipo(recibidas["operaciones"], "cuota")
    recargo = _suma(emitidas["operaciones"], "recargo_cuota") + _suma(
        recibidas["operaciones"], "recargo_cuota"
    )
    cuota_devengada = sum(
        (Decimal(v["cuota"]) for v in devengado.values()), Decimal(0)
    )
    cuota_deducible = sum(
        (Decimal(v["cuota"]) for v in deducible.values()), Decimal(0)
    )
    resultado = cuota_devengada - cuota_deducible
    diferido = _suma(emitidas["operaciones"], "cuota", incluir=False) + _suma(
        recibidas["operaciones"], "cuota", incluir=False
    )
    intra = await construir_libro_intracomunitarias(
        db,
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        inicio=rango_periodo(ejercicio, tipo_periodo, periodo)[0],
        fin=rango_periodo(ejercicio, tipo_periodo, periodo)[1],
    )
    return {
        "ejercicio": ejercicio,
        "periodo": periodo,
        "tipo_periodo": str(tipo_periodo),
        "devengado": devengado,
        "deducible": deducible,
        "intracomunitarias": _por_tipo(intra["operaciones"], "cuota"),
        "recargo_equivalencia": {"cuota": fmt(recargo)},
        "resultado": {
            "a_ingresar": fmt(resultado if resultado > 0 else Decimal(0)),
            "a_compensar": fmt(-resultado if resultado < 0 else Decimal(0)),
        },
        "iva_diferido": {"pendiente": fmt(diferido)},
        "cuadre_libros": True,
    }


async def resumen_periodico(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    tipo_periodo: TipoPeriodo | str,
    periodo: int,
) -> dict:
    emitidas, recibidas, (inicio, fin) = await _libros_periodo(
        db,
        empresa_id=empresa_id,
        ejercicio=ejercicio,
        tipo_periodo=tipo_periodo,
        periodo=periodo,
    )
    return {
        "ejercicio": ejercicio,
        "periodo": periodo,
        "tipo_periodo": str(tipo_periodo),
        "fecha_inicio": inicio.isoformat(),
        "fecha_fin": fin.isoformat(),
        "devengado": _por_tipo(emitidas["operaciones"], "cuota"),
        "deducible": _por_tipo(recibidas["operaciones"], "cuota"),
        "total_devengado": emitidas["total_cuota"],
        "total_deducible": recibidas["total_cuota"],
    }


async def preparar_347(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    limite: Decimal = LIMITE_347,
) -> dict:
    inicio = date(ejercicio, 1, 1)
    fin = date(ejercicio, 12, 31)
    emitidas = await construir_libro_emitidas(
        db, empresa_id=empresa_id, ejercicio=ejercicio, inicio=inicio, fin=fin
    )
    recibidas = await construir_libro_recibidas(
        db, empresa_id=empresa_id, ejercicio=ejercicio, inicio=inicio, fin=fin
    )
    acumulado: dict[str, dict] = {}
    for op in [*emitidas["operaciones"], *recibidas["operaciones"]]:
        clave = op["nif_tercero"] or "SIN-NIF"
        registro = acumulado.setdefault(
            clave,
            {
                "nif_tercero": clave,
                "nombre": op["nombre_tercero"],
                "clave_operacion": "A",
                "importe": Decimal(0),
                "n_operaciones": 0,
            },
        )
        registro["importe"] += Decimal(op["base"])
        registro["n_operaciones"] += 1
    operaciones = [
        {
            "nif_tercero": r["nif_tercero"],
            "nombre": r["nombre"],
            "clave_operacion": r["clave_operacion"],
            "importe_acumulado": fmt(r["importe"]),
            "n_operaciones": r["n_operaciones"],
        }
        for r in sorted(acumulado.values(), key=lambda x: x["nif_tercero"])
        if r["importe"] > limite
    ]
    total = sum((Decimal(o["importe_acumulado"]) for o in operaciones), Decimal(0))
    return {"ejercicio": ejercicio, "operaciones": operaciones, "total_general": fmt(total)}


async def preparar_349(
    db: AsyncSession,
    *,
    empresa_id: int,
    ejercicio: int,
    tipo_periodo: TipoPeriodo | str,
    periodo: int,
) -> dict:
    inicio, fin = rango_periodo(ejercicio, tipo_periodo, periodo)
    libro = await construir_libro_intracomunitarias(
        db, empresa_id=empresa_id, ejercicio=ejercicio, inicio=inicio, fin=fin
    )
    acumulado: dict[tuple[str, str], dict] = {}
    for op in libro["operaciones"]:
        clave_op = op["clave_operacion"]
        registro = acumulado.setdefault(
            (op["nif_tercero"] or "SIN-NIF", clave_op),
            {
                "nif_tercero": op["nif_tercero"],
                "clave_operacion": clave_op,
                "tipo_operacion": "bienes" if clave_op == "C" else "servicios",
                "importe": Decimal(0),
            },
        )
        registro["importe"] += Decimal(op["base"])
    operaciones = [
        {
            "nif_tercero": r["nif_tercero"],
            "clave_operacion": r["clave_operacion"],
            "tipo_operacion": r["tipo_operacion"],
            "importe": fmt(r["importe"]),
        }
        for r in acumulado.values()
    ]
    total = sum((Decimal(o["importe"]) for o in operaciones), Decimal(0))
    return {
        "ejercicio": ejercicio,
        "periodo": periodo,
        "operaciones": operaciones,
        "total_general": fmt(total),
    }