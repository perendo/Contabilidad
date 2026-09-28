"""Previsualización e importación de asientos (SPEC-005 US1/US2)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from services.audit.writer import audit_escribir
from services.importexport.parseador import (
    FilaCruda,
    agrupar_por_asiento,
    parsear_archivo,
    parsear_fecha,
)
from services.importexport.validador import validar_asiento
from services.journal.entry_service import AsientoError, asentar, crear_borrador

CUATRO = Decimal("0.0000")


def _error(fila: int, grupo: str, cuenta: str | None, tipo: str, mensaje: str) -> dict:
    return {
        "fila": fila,
        "grupo_asiento": grupo,
        "cuenta": cuenta,
        "tipo_error": tipo,
        "mensaje": mensaje,
    }


async def _validar_grupos(
    db: AsyncSession, empresa_id: int, filas: list[FilaCruda]
) -> tuple[dict[str, list[FilaCruda]], list[dict], dict[str, dict[str, int]]]:
    grupos = agrupar_por_asiento(filas)
    validos: dict[str, list[FilaCruda]] = {}
    errores: list[dict] = []
    cuentas_por_grupo: dict[str, dict[str, int]] = {}
    for grupo, lineas in grupos.items():
        fallos, cuentas = await validar_asiento(db, empresa_id, grupo, lineas)
        if fallos:
            errores.extend(fallos)
        else:
            validos[grupo] = lineas
            cuentas_por_grupo[grupo] = {code: c.id for code, c in cuentas.items()}
    return validos, errores, cuentas_por_grupo


async def previsualizar_importacion(
    db: AsyncSession, *, empresa_id: int, file_bytes: bytes, nombre: str
) -> dict:
    """Dry-run: validate only, never write to the DB."""
    filas = parsear_archivo(file_bytes, nombre, empresa_id)
    grupos = agrupar_por_asiento(filas)
    validos, errores, _ = await _validar_grupos(db, empresa_id, filas)
    return {
        "total_asientos": len(grupos),
        "asientos_validos": len(validos),
        "asientos_con_error": len(grupos) - len(validos),
        "errores": errores,
    }


async def importar_asientos(
    db: AsyncSession, *, empresa_id: int, file_bytes: bytes, nombre: str, actor: str | None = None
) -> dict:
    """Re-validate and persist only the valid asientos; omit the rest."""
    filas = parsear_archivo(file_bytes, nombre, empresa_id)
    grupos = agrupar_por_asiento(filas)
    validos, errores, cuentas_por_grupo = await _validar_grupos(db, empresa_id, filas)

    importados = 0
    numeros: list[int] = []
    for grupo, lineas in validos.items():
        fecha = parsear_fecha(lineas[0].fecha)
        cuentas = cuentas_por_grupo[grupo]
        payload_lineas = [
            {
                "account_id": cuentas[f.cuenta],
                "debit": str(f.debe.quantize(CUATRO)),
                "credit": str(f.haber.quantize(CUATRO)),
                "detail": f.detalle,
            }
            for f in lineas
        ]
        try:
            async with db.begin_nested():
                borrador = await crear_borrador(
                    db, empresa_id=empresa_id, fecha=fecha,
                    concepto=lineas[0].concepto or f"Asiento importado {grupo}",
                    lineas=payload_lineas, actor=actor,
                )
                entrada = await asentar(
                    db, empresa_id=empresa_id, entry_id=borrador.id, actor=actor
                )
            importados += 1
            if entrada.numero_asiento is not None:
                numeros.append(entrada.numero_asiento)
        except AsientoError as exc:
            errores.append(
                _error(lineas[0].fila, grupo, None, exc.code, str(exc))
            )

    await audit_escribir(
        db,
        empresa_id=empresa_id,
        actor=actor or "system",
        action="IMPORT_ASIENTOS",
        entity="journal_entry",
        payload={
            "total": str(len(grupos)),
            "importados": str(importados),
            "omitidos": str(len(grupos) - importados),
        },
    )
    await db.flush()
    return {
        "asientos_importados": importados,
        "asientos_omitidos": len(grupos) - importados,
        "primer_numero_asiento": min(numeros) if numeros else None,
        "ultimo_numero_asiento": max(numeros) if numeros else None,
        "omisiones": errores,
    }
