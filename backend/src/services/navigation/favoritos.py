"""Favoritos de navegacion (SPEC-031, US4).

Preferencias del usuario, no datos contables. Es la unica parte de la feature que
**escribe**, y por eso es la unica que tiene que auditar (constitution, seccion de
stack: "registro obligatorio de cada operacion de escritura").

EL LIMITE DE CINCO OPERA EN LA LECTURA, NO EN LA ESCRITURA (CHK025)

Durante la revision del checklist aparecio una contradiccion real entre cuatro
artefactos: el caso borde del spec y `research.md` decian que un favorito por encima
del maximo se recorta y se guarda; el contrato y las tareas decian 422. **Gana el
recorte**, por un motivo concreto: si la escritura rechazara el sexto, el usuario que
ya tiene cinco favoritos no podria anadir el suyo, que es justo lo que el requisito
prohibe ("MUST NOT perder los que excedan ese limite"). Un recorte es reversible por
el usuario; un rechazo no.

Asi que aqui no hay ningun limite. `marcar` acepta el sexto, el septimo y los que
sean; `listar` recorta a cinco e informa cuantos hay y cuantos se ven, para que la
interfaz pueda avisar y ofrecer desplegar el resto.

LO UNICO QUE SI SE RECHAZA EN ESCRITURA

`orden` no positivo, que es una peticion malformada y no una operacion valida. Es un
`422` distinto del que seria "ya tienes demasiados", precisamente para que el cliente
pueda distinguirlos.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from models.navigation.favorito import FavoritoUsuario
from services.audit import registrar_auditoria
from services.navigation.destinos import es_accesible, es_conocido
from services.navigation.errores import (
    CONJUNTO_INCOMPLETO,
    DESTINO_DESCONOCIDO,
    ORDEN_FUERA_DE_RANGO,
    error,
)

#: Maximo VISIBLE. La base de datos no impone ninguno (ver el docstring del modulo).
#: Se importa del catalogo en vez de repetirse, para que el panel, el contrato y el
#: servicio no puedan afirmar tres numeros distintos; `test_destinos_en_sync.py` vigila
#: que siga siendo 5.
MAXIMO_VISIBLES = 5

#: Operaciones de auditoria. Los nombres van en mayusculas por convencion del repo.
OPERACION_MARCAR = "FAVORITO_MARCAR"
OPERACION_DESMARCAR = "FAVORITO_DESMARCAR"
OPERACION_REORDENAR = "FAVORITO_REORDENAR"

#: Entidad en `audit_log`, para poder consultar los favoritos de un usuario.
ENTIDAD = "favorito"


async def marcar(
    db: AsyncSession,
    *,
    empresa_id: int,
    usuario_id: int,
    destino: str,
    orden: int,
    actor: str | None = None,
    ip: str | None = None,
) -> FavoritoUsuario:
    """Marca un destino como favorito. Idempotente.

    Marcar dos veces el mismo destino no es un error: es lo que pasa al pulsar el
    boton en dos pestanas, que es un gesto normal del usuario. Si ya estaba, se
    actualiza el orden en vez de insertar una segunda fila.
    """
    if orden < 1:
        raise error(
            ORDEN_FUERA_DE_RANGO,
            "La posicion del favorito debe ser un entero positivo.",
        )
    if not es_conocido(destino.strip()):
        # 404, no 422: no es un dato mal formado, es un destino que no existe. Y tiene
        # que fallar **antes** de tocar la base, porque un favorito de una clave
        # desconocida crearia una fila que ninguna superficie puede abrir ni el usuario
        # puede quitar: seria un favorito invisible de forma permanente.
        raise error(
            DESTINO_DESCONOCIDO,
            f"'{destino.strip()}' no es un destino del mapa de navegacion.",
            status_code=404,
        )

    limpio = destino.strip()
    existente = await db.scalar(
        sa.select(FavoritoUsuario).where(
            FavoritoUsuario.empresa_id == empresa_id,
            FavoritoUsuario.usuario_id == usuario_id,
            FavoritoUsuario.destino == limpio,
        )
    )
    if existente is not None:
        existente.orden = orden
        await db.flush()
        return existente

    fila = FavoritoUsuario(
        empresa_id=empresa_id,
        usuario_id=usuario_id,
        destino=limpio,
        orden=orden,
    )
    db.add(fila)
    await db.flush()
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        usuario=actor,
        ip=ip,
        operacion=OPERACION_MARCAR,
        entidad=ENTIDAD,
        entidad_id=limpio,
        payload={"orden": orden},
    )
    return fila


async def desmarcar(
    db: AsyncSession,
    *,
    empresa_id: int,
    usuario_id: int,
    destino: str,
    actor: str | None = None,
    ip: str | None = None,
) -> bool:
    """Desmarca un destino. Idempotente: si no estaba, no pasa nada.

    Devuelve `True` si habia algo que borrar, para que la API pueda distinguir, y para
    que la auditoria no registre un borrado que no ocurrio.
    """
    fila = await db.scalar(
        sa.select(FavoritoUsuario).where(
            FavoritoUsuario.empresa_id == empresa_id,
            FavoritoUsuario.usuario_id == usuario_id,
            FavoritoUsuario.destino == destino.strip(),
        )
    )
    if fila is None:
        return False
    await db.delete(fila)
    await db.flush()
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        usuario=actor,
        ip=ip,
        operacion=OPERACION_DESMARCAR,
        entidad=ENTIDAD,
        entidad_id=destino.strip(),
        payload={"orden": fila.orden},
    )
    return True


async def listar(
    db: AsyncSession,
    *,
    empresa_id: int,
    usuario_id: int,
    accesibles: set[tuple[str, str]] | None = None,
) -> dict[str, object]:
    """Los favoritos del usuario, con `total` y `visibles` (CHK025).

    `items` trae como mucho `MAXIMO_VISIBLES` entradas, ordenadas. `total` es cuantos
    hay guardados, que puede ser mayor. La diferencia entre ambos es lo que permite a
    la interfaz avisar de que hay favoritos ocultos **sin perderlos**.

    `accesibles` es el conjunto de destinos a los que el usuario puede llegar, y lo pasa
    la API, que es quien conoce sus permisos. Por defecto vale `None`, que se interpreta
    como "todos los conocidos son accesibles": es lo que necesitan los tests de servicio
    y lo que evita que un `None` descuidado convierta el favourite de un usuario en algo
    invisible. Un destino ausente del mapa se marca `desconocido: true` pase lo que pase,
    porque eso no depende de permisos sino de que la ruta se haya reubicado.
    """
    filas = (
        (
            await db.scalars(
                sa.select(FavoritoUsuario)
                .where(
                    FavoritoUsuario.empresa_id == empresa_id,
                    FavoritoUsuario.usuario_id == usuario_id,
                )
                .order_by(FavoritoUsuario.orden, FavoritoUsuario.destino)
            )
        )
        .all()
    )
    visibles = filas[:MAXIMO_VISIBLES]
    items = []
    for f in visibles:
        items.append(
            {
                "destino": f.destino,
                "orden": f.orden,
                "accesible": es_accesible(f.destino, accesibles),
                "desconocido": not es_conocido(f.destino),
            }
        )
    return {
        "items": items,
        "total": len(filas),
        "visibles": len(visibles),
    }


async def reordenar(
    db: AsyncSession,
    *,
    empresa_id: int,
    usuario_id: int,
    ordenes: list[str],
    actor: str | None = None,
    ip: str | None = None,
) -> dict[str, object]:
    """Fija el orden del conjunto completo.

    Exige que `ordenes` contenga **exactamente** los destinos actuales, sin repeticiones
    y sin omitir ninguno. Es deliberado: un reordenado parcial no dice nada de donde va
    el destino que falta, y cada interpretacion posible derrota al usuario. Un
    `PATCH` con dos de tres elementos, en lugar de fallar, dejaria el conjunto en un
    estado que nadie pidio y que no sabe reproducir.
    """
    actuales = (
        (
            await db.scalars(
                sa.select(FavoritoUsuario.destino).where(
                    FavoritoUsuario.empresa_id == empresa_id,
                    FavoritoUsuario.usuario_id == usuario_id,
                )
            )
        )
        .all()
    )
    set_actuales = set(actuales)
    if len(ordenes) != len(set(ordenes)) or set(ordenes) != set_actuales:
        raise error(
            CONJUNTO_INCOMPLETO,
            "El reordenado debe contener exactamente los favoritos actuales, "
            "sin repeticiones y sin omitir ninguno.",
        )

    for posicion, destino in enumerate(ordenes, start=1):
        fila = await db.scalar(
            sa.select(FavoritoUsuario).where(
                FavoritoUsuario.empresa_id == empresa_id,
                FavoritoUsuario.usuario_id == usuario_id,
                FavoritoUsuario.destino == destino,
            )
        )
        if fila is not None:
            fila.orden = posicion
    await db.flush()
    await registrar_auditoria(
        db,
        empresa_id=empresa_id,
        usuario=actor,
        ip=ip,
        operacion=OPERACION_REORDENAR,
        entidad=ENTIDAD,
        entidad_id=None,
        payload={"ordenes": ordenes},
    )
    return await listar(db, empresa_id=empresa_id, usuario_id=usuario_id)
