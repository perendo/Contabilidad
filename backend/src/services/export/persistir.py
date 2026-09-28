"""Persistencia ACID de la exportacion (SPEC-029 T021/T022, research D9/D10).

`exportar_tenant` es el orquestador: recorre el catalogo de bloques, recopila
con filtro de empresa, genera el ZIP determinista y persiste `Exportacion` +
`BlobExportacion` + `ManifiestoExportacion` + `ManifiestoBloque` + audit log
**en una sola transaccion**. El boundary ACID autoritativo del proyecto es
`get_db` (commit al final de la peticion, rollback ante excepcion), asi que aqui
se hace `flush()` y nunca `async with async_session.begin()`.

Numeracion (constitution IV): `numero_exportacion` correlativo por
`(empresa_id, anio_creacion)`, con `SELECT ... FOR UPDATE` sobre la ultima fila
del par y el UNIQUE como red final. Sin `FOR UPDATE` (SQLite no lo soporta) el
UNIQUE sigue garantizando que no haya dos exportaciones con el mismo numero.

Inmutabilidad (research D9): la cabecera nace `en_proceso` y solo se actualiza a
`lista`/`fallida`; el trigger `chk_exportacion_immutable` bloquea cualquier
cambio posterior. Todo el trabajo ocurre dentro de un `SAVEPOINT`: si algo falla,
se deshace y se registra una cabecera `fallida` con su `mensaje_error`, de modo
que el fallo queda auditado sin dejar datos a medias.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.export.blob_exportacion import BlobExportacion
from models.export.exportacion import (
    EstadoExportacion,
    Exportacion,
    TipoExportacion,
)
from models.export.manifiesto import (
    FORMATO_VERSION,
    ManifiestoBloque,
    ManifiestoExportacion,
)
from services.audit import registrar_auditoria
from services.export.bloques import (
    BLOQUES_OBLIGATORIOS,
    bloque_por_nombre,
    ruta_por_nombre,
)
from services.export.errores import error
from services.export.manifiesto import lineas_manifiesto
from services.export.recopilar import BloqueRecopilado, recopilar_bloque
from services.export.sii import config_efectiva, entradas_sii
from services.export.zip_generator import escribir_zip

__all__ = [
    "MAX_INTENTOS_NUMERO",
    "asignar_numero",
    "exportar_tenant",
    "listar_exportaciones",
    "obtener_exportacion",
    "resumen_exportacion",
    "validar_rango",
]

#: Reintentos ante colision del UNIQUE de numeracion (dos altas simultaneas).
MAX_INTENTOS_NUMERO: int = 3

#: Constantes de operacion de auditoria (research D9).
AUDITAR = "GENERAR_EXPORTACION"
AUDITAR_FALLIDA = "GENERAR_EXPORTACION_FALLIDA"


def ahora() -> datetime:
    """Instante de generacion en UTC, truncado al segundo."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def validar_rango(ejercicio_desde: int | None, ejercicio_hasta: int | None) -> None:
    """FR-005: rango coherente; ambos nulos significan "exportar todo"."""
    if ejercicio_desde is None and ejercicio_hasta is None:
        return
    if ejercicio_desde is None or ejercicio_hasta is None:
        raise error(
            "rango_incompleto",
            "Indica ejercicio_desde y ejercicio_hasta, o ninguno de los dos",
            422,
        )
    if ejercicio_desde > ejercicio_hasta:
        raise error(
            "rango_invalido",
            f"ejercicio_desde ({ejercicio_desde}) es mayor que ejercicio_hasta ({ejercicio_hasta})",
            422,
        )


async def _ultimo_numero(
    db: AsyncSession, empresa_id: int, anio: int
) -> int | None:
    """Ultimo numero emitido del par, con `SELECT ... FOR UPDATE` atomico."""
    consulta = (
        select(Exportacion.numero_exportacion)
        .where(Exportacion.empresa_id == empresa_id, Exportacion.anio_creacion == anio)
        .order_by(Exportacion.numero_exportacion.desc())
        .limit(1)
        .with_for_update()
    )
    return await db.scalar(consulta)


async def asignar_numero(db: AsyncSession, empresa_id: int, anio: int) -> int:
    """Siguiente correlativo por `(empresa_id, anio_creacion)` (constitution IV)."""
    for intento in range(MAX_INTENTOS_NUMERO):
        ultimo = await _ultimo_numero(db, empresa_id, anio)
        numero = (ultimo or 0) + 1
        existe = await db.scalar(
            select(Exportacion.id).where(
                Exportacion.empresa_id == empresa_id,
                Exportacion.anio_creacion == anio,
                Exportacion.numero_exportacion == numero,
            )
        )
        if existe is None:
            return numero
        if intento == MAX_INTENTOS_NUMERO - 1:
            raise error(
                "numeracion_en_conflicto",
                "No se pudo asignar el numero correlativo de exportacion",
                409,
            )
    raise error(
        "numeracion_en_conflicto", "No se pudo asignar el numero de exportacion", 409
    )


def _manifiesto_lineas(
    inventario: list[BloqueRecopilado], empresa_id: int, manifiesto_id: uuid.UUID
) -> list[ManifiestoBloque]:
    lineas: list[ManifiestoBloque] = []
    for linea in lineas_manifiesto(inventario):
        lineas.append(
            ManifiestoBloque(
                id=uuid.uuid4(),
                empresa_id=empresa_id,
                manifiesto_id=manifiesto_id,
                bloque=str(linea["bloque"]),
                entidades_exportadas=",".join(linea["entidades_exportadas"])[:100],
                conteo_registros=int(linea["conteo_registros"]),
                sha256=linea["sha256"],
                fecha_min=linea["fecha_min"],
                fecha_max=linea["fecha_max"],
                ejercicio_min=linea["ejercicio_min"],
                ejercicio_max=linea["ejercicio_max"],
            )
        )
    return lineas


async def _generar(
    db: AsyncSession,
    empresa_id: int,
    tipo: TipoExportacion,
    ejercicio_desde: int | None,
    ejercicio_hasta: int | None,
    fecha: datetime,
    numero: int,
    creado_por: str | None,
) -> dict[str, Any]:
    """Trabajo de la generacion, dentro del SAVEPOINT de `exportar_tenant`."""
    cabecera = Exportacion(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        anio_creacion=fecha.year,
        numero_exportacion=numero,
        tipo=tipo,
        ejercicio_desde=ejercicio_desde,
        ejercicio_hasta=ejercicio_hasta,
        estado=EstadoExportacion.en_proceso,
        creado_por=creado_por,
        created_at=fecha,
    )
    db.add(cabecera)
    await db.flush()

    bloques: list[BloqueRecopilado] = []
    for bloque in BLOQUES_OBLIGATORIOS:
        bloques.append(
            await recopilar_bloque(db, bloque, empresa_id, ejercicio_desde, ejercicio_hasta)
        )

    entradas_extra: dict[str, bytes] = {}
    config = await config_efectiva(db, empresa_id)
    if tipo == TipoExportacion.SII or config.obligado_sii:
        entradas, _registros, _cfg = await entradas_sii(
            db,
            empresa_id,
            ejercicio_desde=ejercicio_desde,
            ejercicio_hasta=ejercicio_hasta,
        )
        entradas_extra.update(entradas)

    zipio = escribir_zip(
        empresa_id,
        bloques,
        ejercicio_desde=ejercicio_desde,
        ejercicio_hasta=ejercicio_hasta,
        fecha_generacion=fecha,
        tipo=tipo.value,
        numero_exportacion=numero,
        entradas_extra=entradas_extra,
    )

    blob = BlobExportacion(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        exportacion_id=cabecera.id,
        contenido=zipio.contenido,
        sha256=zipio.sha256,
        tamano_bytes=zipio.tamano_bytes,
        created_at=fecha,
    )
    db.add(blob)
    await db.flush()

    manifiesto = ManifiestoExportacion(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        exportacion_id=cabecera.id,
        formato_version=FORMATO_VERSION,
        fecha_generacion=fecha,
        tenant_id=empresa_id,
        n_bloques=zipio.n_bloques,
        sha256_fichero=zipio.sha256,
    )
    db.add(manifiesto)
    await db.flush()
    for linea in _manifiesto_lineas(zipio.inventario, empresa_id, manifiesto.id):
        db.add(linea)

    cabecera.estado = EstadoExportacion.lista
    cabecera.completado_at = fecha
    cabecera.blob_id = blob.id
    cabecera.sha256 = zipio.sha256
    cabecera.tamano_bytes = zipio.tamano_bytes
    cabecera.n_bloques = zipio.n_bloques
    await db.flush()
    return {
        "exportacion": cabecera,
        "manifiesto": manifiesto,
        "sha256_contenido": zipio.sha256_contenido,
        "config_sii": config,
    }


async def _registrar_fallo(
    db: AsyncSession,
    empresa_id: int,
    tipo: TipoExportacion,
    ejercicio_desde: int | None,
    ejercicio_hasta: int | None,
    fecha: datetime,
    creado_por: str | None,
    actor_numero: int,
    motivo: Exception,
) -> None:
    """Cabecera `fallida` con su `mensaje_error` (el SAVEPOINT ya se deshizo)."""
    fallida = Exportacion(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        anio_creacion=fecha.year,
        numero_exportacion=actor_numero,
        tipo=tipo,
        ejercicio_desde=ejercicio_desde,
        ejercicio_hasta=ejercicio_hasta,
        estado=EstadoExportacion.fallida,
        creado_por=creado_por,
        created_at=fecha,
        completado_at=fecha,
        n_bloques=0,
        mensaje_error=f"{type(motivo).__name__}: {motivo}"[:2000],
    )
    db.add(fallida)
    await db.flush()
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        operacion=AUDITAR_FALLIDA,
        entidad="Exportacion",
        entidad_id=fallida.id,
        payload={
            "tipo": tipo.value,
            "ejercicio_desde": ejercicio_desde,
            "ejercicio_hasta": ejercicio_hasta,
            "error": fallida.mensaje_error,
        },
        usuario=creado_por,
    )


async def exportar_tenant(
    db: AsyncSession,
    *,
    empresa_id: int,
    tipo: TipoExportacion = TipoExportacion.INTEGRAL,
    ejercicio_desde: int | None = None,
    ejercicio_hasta: int | None = None,
    actor: str | None = None,
    ip: str | None = None,
    fecha: datetime | None = None,
) -> dict[str, Any]:
    """Genera y persiste la exportacion integral de la empresa activa.

    Si cualquier paso falla, se deshace el SAVEPOINT (no queda una exportacion a
    medias), se registra una cabecera `fallida` con su `mensaje_error` y se
    propaga el error al router, que lo traduce a 4xx/5xx.
    """
    validar_rango(ejercicio_desde, ejercicio_hasta)
    momento = fecha or ahora()
    numero = await asignar_numero(db, empresa_id, momento.year)
    try:
        async with db.begin_nested():
            resultado = await _generar(
                db,
                empresa_id,
                tipo,
                ejercicio_desde,
                ejercicio_hasta,
                momento,
                numero,
                actor,
            )
    except Exception as exc:
        await db.rollback()
        numero = await asignar_numero(db, empresa_id, momento.year)
        await _registrar_fallo(
            db,
            empresa_id,
            tipo,
            ejercicio_desde,
            ejercicio_hasta,
            momento,
            actor,
            numero,
            exc,
        )
        # El `fallida` debe sobrevivir al rollback del boundary `get_db` que
        # provoke la excepcion: se confirma aqui, en su propia transaccion.
        await db.commit()
        raise
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        operacion=AUDITAR,
        entidad="Exportacion",
        entidad_id=resultado["exportacion"].id,
        payload={
            "tipo": tipo.value,
            "numero_exportacion": numero,
            "anio_creacion": momento.year,
            "ejercicio_desde": ejercicio_desde,
            "ejercicio_hasta": ejercicio_hasta,
            "n_bloques": resultado["exportacion"].n_bloques,
            "sha256": resultado["exportacion"].sha256,
            "sha256_contenido": resultado["sha256_contenido"],
        },
        usuario=actor,
        ip=ip,
    )
    return resultado


async def obtener_exportacion(
    db: AsyncSession, empresa_id: int, exportacion_id: uuid.UUID
) -> Exportacion:
    """Cabecera de la exportacion **de la empresa activa** o 404 (aislamiento)."""
    fila = await db.scalar(
        select(Exportacion).where(
            Exportacion.empresa_id == empresa_id, Exportacion.id == exportacion_id
        )
    )
    if fila is None:
        raise error("exportacion_no_encontrada", "Exportacion inexistente en la empresa activa", 404)
    return fila


async def obtener_manifiesto(
    db: AsyncSession, empresa_id: int, exportacion_id: uuid.UUID
) -> tuple[ManifiestoExportacion, list[ManifiestoBloque]] | None:
    """Cabecera y lineas del manifiesto, o None."""
    cabecera = await db.scalar(
        select(ManifiestoExportacion).where(
            ManifiestoExportacion.empresa_id == empresa_id,
            ManifiestoExportacion.exportacion_id == exportacion_id,
        )
    )
    if cabecera is None:
        return None
    lineas = list(
        (
            await db.scalars(
                select(ManifiestoBloque)
                .where(
                    ManifiestoBloque.empresa_id == empresa_id,
                    ManifiestoBloque.manifiesto_id == cabecera.id,
                )
                .order_by(ManifiestoBloque.bloque)
            )
        ).all()
    )
    return cabecera, lineas


async def obtener_blob(
    db: AsyncSession, empresa_id: int, exportacion_id: uuid.UUID
) -> BlobExportacion:
    """Binario del ZIP de la exportacion, o 404."""
    fila = await db.scalar(
        select(BlobExportacion).where(
            BlobExportacion.empresa_id == empresa_id,
            BlobExportacion.exportacion_id == exportacion_id,
        )
    )
    if fila is None:
        raise error("exportacion_sin_contenido", "La exportacion no tiene blob almacenado", 404)
    return fila


async def listar_exportaciones(
    db: AsyncSession,
    *,
    empresa_id: int,
    tipo: str | None = None,
    estado: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """Listado paginado con filtros de tipo y estado."""
    filtros = [Exportacion.empresa_id == empresa_id]
    if tipo:
        filtros.append(Exportacion.tipo == TipoExportacion(tipo))
    if estado:
        filtros.append(Exportacion.estado == EstadoExportacion(estado))
    total = int(
        await db.scalar(select(func.count()).select_from(Exportacion).where(*filtros)) or 0
    )
    filas = (
        await db.scalars(
            select(Exportacion)
            .where(*filtros)
            .order_by(Exportacion.created_at.desc(), Exportacion.numero_exportacion.desc())
            .limit(page_size)
            .offset((max(page, 1) - 1) * page_size)
        )
    ).all()
    return {"items": [resumen_exportacion(f) for f in filas], "total": total, "page": max(page, 1)}


def resumen_exportacion(fila: Exportacion) -> dict[str, Any]:
    """Resumen serializable de la cabecera (sin el manifiesto)."""
    return {
        "exportacion_id": str(fila.id),
        "numero_exportacion": fila.numero_exportacion,
        "anio_creacion": fila.anio_creacion,
        "tipo": fila.tipo.value,
        "estado": fila.estado.value,
        "ejercicio_desde": fila.ejercicio_desde,
        "ejercicio_hasta": fila.ejercicio_hasta,
        "creado_por": fila.creado_por,
        "created_at": fila.created_at.isoformat() if fila.created_at else None,
        "completado_at": fila.completado_at.isoformat() if fila.completado_at else None,
        "sha256": fila.sha256,
        "tamano_bytes": fila.tamano_bytes,
        "tamano_mb": f"{fila.por_megabytes:0.4f}",
        "n_bloques": fila.n_bloques,
        "mensaje_error": fila.mensaje_error,
    }


def detalle_exportacion(
    fila: Exportacion,
    manifiesto: ManifiestoExportacion | None,
    lineas: list[ManifiestoBloque],
) -> dict[str, Any]:
    """Detalle con el inventario de bloques (`contracts/api-contracts.md`)."""
    detalle = resumen_exportacion(fila)
    bloques: list[dict[str, Any]] = []
    for linea in sorted(lineas, key=lambda l: l.bloque):
        bloque = bloque_por_nombre(linea.bloque)
        bloques.append(
            {
                "bloque": linea.bloque,
                "fichero": bloque.fichero if bloque else None,
                "ruta": ruta_por_nombre(linea.bloque),
                "descripcion": bloque.descripcion if bloque else None,
                "entidades_exportadas": linea.entidades_exportadas.split(",")
                if linea.entidades_exportadas
                else [],
                "conteo_registros": linea.conteo_registros,
                "sha256": linea.sha256,
                "fecha_min": linea.fecha_min.isoformat() if linea.fecha_min else None,
                "fecha_max": linea.fecha_max.isoformat() if linea.fecha_max else None,
                "ejercicio_min": linea.ejercicio_min,
                "ejercicio_max": linea.ejercicio_max,
            }
        )
    detalle["manifiesto"] = {
        "id": str(manifiesto.id) if manifiesto else None,
        "formato_version": manifiesto.formato_version if manifiesto else None,
        "fecha_generacion": manifiesto.fecha_generacion.isoformat()
        if manifiesto and manifiesto.fecha_generacion
        else None,
        "tenant_id": manifiesto.tenant_id if manifiesto else fila.empresa_id,
        "ejercicio_desde": fila.ejercicio_desde,
        "ejercicio_hasta": fila.ejercicio_hasta,
        "n_bloques": manifiesto.n_bloques if manifiesto else 0,
        "sha256_fichero": manifiesto.sha256_fichero if manifiesto else fila.sha256,
        "bloques": bloques,
    }
    return detalle


def contrato_cabecera(fila: Exportacion) -> dict[str, Any]:
    """Cabecera de la peticion de creacion, con el tamano tambien en MiB."""
    return {**resumen_exportacion(fila), "descargable": fila.descargable}


__all__ += [
    "contrato_cabecera",
    "detalle_exportacion",
    "obtener_blob",
    "obtener_manifiesto",
]
