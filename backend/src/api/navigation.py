"""Contexto de sesion y favoritos (SPEC-031, US1 y US4).

`GET /api/v1/contexto` es la unica lectura que el shell necesita: quien eres, en que
empresa estas, en que ejercicio y cuantos asientos lleva cada uno. Antes, pintar la
zona de contexto obligaba al cliente a compositionar varias llamadas y a adivinar
cual era el ejercicio vigente.

Los cuatro endpoints de favoritos son la unica parte de la feature que **escribe**, y la
unica que audita. `empresa_id` NO aparece en el path ni en el body: viene de la sesion
por `get_empresa_id`, igual que en las otras 279 rutas del proyecto (constitution III).
`X-Ejercicio-Activa` si la acepta el cliente, y por eso se valida contra esa misma
empresa antes de usarse: es un filtro interno del tenant, no una frontera de tenant.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import (
    _relacion_activa,
    get_current_user,
    get_empresa_id,
    require_permission,
)
from database import get_db
from models.iam.company import Company
from models.iam.user import User
from services.navigation import ejercicio_activo as validacion
from services.navigation import favoritos as fav
from services.navigation import resumenes
from services.navigation.contexto import elegir_activo, listar_ejercicios
from services.navigation.errores import NavigationError
from services.security.autorizacion import rol_de_empresa
from services.security.matriz import mis_permisos

router = APIRouter(prefix="/api/v1/contexto", tags=["contexto"])

#: Los favoritos cuelgan de su propio router porque el prefijo es otro. Un solo
#: `APIRouter` no puede servir `/contexto` y `/favoritos` sin montar cada endpoint dos
#: veces, y un `include_router` con prefijo y camino vacios es error de FastAPI.
favoritos_router = APIRouter(prefix="/api/v1/favoritos", tags=["favoritos"])

#: Los resúmenes de superficie cuelgan de su propio router porque el prefijo es otro
#: (`/api/v1/resumenes`), igual que los favoritos. Un `APIRouter` no puede servir dos
#: prefijos, y un `include_router` con prefijo y camino vacios es error de FastAPI.
resumenes_router = APIRouter(prefix="/api/v1/resumenes", tags=["resumenes"])

EmpresaDep = Annotated[int, Depends(get_empresa_id)]
SesionDep = Annotated[AsyncSession, Depends(get_db)]
UsuarioDep = Annotated[User, Depends(get_current_user)]


@router.get(
    "",
    summary="Contexto de sesion: usuario, empresa, ejercicio activo y listados",
    dependencies=[Depends(require_permission("acct", "ver"))],
)
async def obtener_contexto(
    request: Request,
    empresa_id: EmpresaDep,
    session: SesionDep,
    user: UsuarioDep,
) -> dict[str, Any]:
    """Devuelve el contexto completo en una llamada.

    El guard es `acct:ver` porque es el permiso mas ampliamente concedido del
    catalogo: los tres roles base lo poseen. Es lo que permite que cualquiera con
    acceso a la contabilidad pinte el shell, que es el requisito (FR-006, redactado
    como propiedad y no como nombre de permiso).
    """
    try:
        # 1. Se interpreta la cabecera antes de tocar la base de datos. Un valor
        #    mal formado es un error de sintaxis del cliente, no de negocio.
        solicitado = validacion.parsear(request.headers.get("X-Ejercicio-Activa"))

        # 2. Los ejercicios de ESTA empresa. El filtro por `empresa_id` esta dentro
        #    del servicio y es la unica barrera que impide el aislamiento (V(b)).
        filas = await listar_ejercicios(session, empresa_id=empresa_id)

        # 3. El ejercicio pedido se valida contra esas filas. Este es el punto en el
        #    que una cabecera manipulada deja de serlo: un ejercicio de otra empresa
        #    o cerrado no se resuelve.
        validacion.validar_solicitado(filas, solicitado)

        # 4. Resolucion del activo: el pedido si es valido, el ano en curso si no.
        activo = elegir_activo(filas, solicitado)
    except NavigationError as exc:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=exc.status_code, detail={"code": exc.code, "detail": exc.detail}
        ) from exc

    empresa = await session.get(Company, empresa_id)
    # El rol se resuelve por la RELACION del usuario con la empresa, no por el
    # usuario: el mismo usuario puede ser ADMIN en una empresa y READ_ONLY en otra,
    # asi que pedir el rol "del usuario" seria una respuesta sin sentido. Es el
    # mismo camino que usa `require_permission` de SPEC-015.
    relacion = await _relacion_activa(session, user.id, empresa_id)
    rol = None
    if relacion is not None:
        rol = await rol_de_empresa(session, empresa_id, relacion.role.name)

    activo_fila = next(
        (f for f in filas if f["ejercicio"] == activo),
        {
            "ejercicio": activo if activo is not None else 0,
            "estado": "cerrado",
            "es_actual": False,
            "n_asientos": 0,
            "es_seleccionable": False,
        },
    )

    return {
        "usuario": {
            "id": user.id,
            "email": user.email,
            "nombre": user.full_name,
            # `rol_de_empresa` devuelve la fila `Rol`, no un enum: el nombre del rol
            # esta en `nombre`, no en `value`. Un `getattr(rol, "value", None)`
            # devolvria `None` siempre y el cliente receberia un usuario sin rol.
            "rol": rol.nombre if rol is not None else None,
        },
        "empresa": {
            "id": empresa_id,
            "nombre": empresa.razon_social if empresa is not None else None,
            "nif": empresa.nif if empresa is not None else None,
            "es_activa": bool(empresa.is_active) if empresa is not None else False,
        },
        "ejercicio_activo": dict(activo_fila),
        "ejercicios": [dict(f) for f in filas],
    }


# ---------------------------------------------------------------------------
# US4 · Favoritos
# ---------------------------------------------------------------------------


class MarcarFavoritoBody(BaseModel):
    """Cuerpo de `PUT /favoritos/{destino}`.

    El destino viaja en el path, no aqui, para que la ruta sea la que identifica el
    recurso. Se repite en el cuerpo solo porque el contrato lo define asi; si no
    coincidieran, manda el path, que es el unico que el cliente no puede cambiar al
    vuelo sin reescribir la peticion.

    `orden` NO declara `ge=1` a proposito. Si lo hiciera, FastAPI responderia con su
    propio 422 de validacion, que es una lista de errores de pydantic y no el sobre
    `{code, detail}` que el contrato define y que el cliente ya sabe leer. Se deja que
    el servicio rechace el valor, y asi todos los errores de esta feature viajan con la
    misma forma.
    """

    destino: str = Field(min_length=1)
    orden: int


class ReordenarFavoritosBody(BaseModel):
    ordenes: list[str] = Field(min_length=1)


def _error(exc: NavigationError) -> HTTPException:
    """Traduce el error de dominio a la respuesta que espera el contrato.

    `NavigationError` lleva su propio `status_code` porque no todos los fallos de esta
    feature son 422: un destino inexistente es 404, y un desmarcar de algo que no
    estaba no es error ninguno.
    """
    return HTTPException(
        status_code=exc.status_code, detail={"code": exc.code, "detail": exc.detail}
    )


async def _permisos_del_usuario(
    session: AsyncSession, user: User, empresa_id: int
) -> set[tuple[str, str]] | None:
    """Los `(modulo, operacion)` del usuario, para marcar `accesible`.

    Se resuelve por la RELACION del usuario con la empresa, no por el usuario: el mismo
    usuario puede ser ADMIN en una empresa y READ_ONLY en otra, y el conjunto de
    destinos alcanzables depende de la empresa activa.

    Devuelve `None` si el usuario no tiene relacion activa, que el servicio interpreta
    como "sin informacion": es preferible mostrar un favorito a esconderlo sin motivo.
    """
    relacion = await _relacion_activa(session, user.id, empresa_id)
    if relacion is None:
        return None
    rol = await rol_de_empresa(session, empresa_id, relacion.role.name)
    if rol is None:
        return None
    matriz = await mis_permisos(session, empresa_id, rol.id)
    return {(p["modulo"], p["operacion"]) for p in matriz.get("permisos", [])}


@favoritos_router.get(
    "",
    summary="Favoritos del usuario en la empresa activa",
    dependencies=[Depends(require_permission("acct", "ver"))],
)
async def obtener_favoritos(
    empresa_id: EmpresaDep, session: SesionDep, user: UsuarioDep
) -> dict[str, Any]:
    """Favoritos con `accesible` y `desconocido`, para ocultar sin borrar (FR-024).

    Los destinos sin permiso o ya reubicados **se conservan**: el cliente los oculta y
    puede ofrecer retirarlos, pero la fila sigue ahí para reaparecer si el permiso
    vuelve. Borrarlos sería perder la preferencia del usuario sin que nadie lo pidiera.
    """
    concedidos = await _permisos_del_usuario(session, user, empresa_id)
    return await fav.listar(
        session,
        empresa_id=empresa_id,
        usuario_id=user.id,
        accesibles=concedidos,
    )


@favoritos_router.put(
    "/{destino}",
    summary="Marcar un destino como favorito",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("acct", "editar"))],
)
async def marcar_favorito(
    destino: str,
    body: MarcarFavoritoBody,
    request: Request,
    empresa_id: EmpresaDep,
    session: SesionDep,
    user: UsuarioDep,
) -> dict[str, Any]:
    """Marca. Idempotente, y **sin limite en la escritura**.

    Un sexto favorito se guarda con 201 y la respuesta es la misma que para el primero.
    El recorte a cinco ocurre en la lectura. Rechazar aquí dejaría al usuario con cinco
    favoritos sin poder añadir el suyo, que es lo que el requisito prohíbe.

    Si la clave del body no coincide con la del path, manda el path: es lo unico que no
    se puede cambiar sin reescribir la URL.
    """
    if body.destino != destino:
        body = body.model_copy(update={"destino": destino})
    try:
        fila = await fav.marcar(
            session,
            empresa_id=empresa_id,
            usuario_id=user.id,
            destino=destino,
            orden=body.orden,
            actor=user.email,
            ip=request.client.host if request.client else None,
        )
    except NavigationError as exc:
        raise _error(exc) from exc
    return {"destino": fila.destino, "orden": fila.orden}


@favoritos_router.delete(
    "/{destino}",
    summary="Desmarcar un destino",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("acct", "editar"))],
)
async def desmarcar_favorito(
    destino: str,
    request: Request,
    empresa_id: EmpresaDep,
    session: SesionDep,
    user: UsuarioDep,
) -> Response:
    """Desmarca. Idempotente: si no estaba, responde 204 igual.

    No se responde 404 por un destino no favorito a proposito: desmarcar dos veces, o
    desmarcar desde una pestana que ya no tenia el favorito, es un estado normal del
    cliente y no un error que merezca correccion.
    """
    try:
        await fav.desmarcar(
            session,
            empresa_id=empresa_id,
            usuario_id=user.id,
            destino=destino,
            actor=user.email,
            ip=request.client.host if request.client else None,
        )
    except NavigationError as exc:
        raise _error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@favoritos_router.patch(
    "",
    summary="Reordenar el conjunto completo de favoritos",
    dependencies=[Depends(require_permission("acct", "editar"))],
)
async def reordenar_favoritos(
    body: ReordenarFavoritosBody,
    request: Request,
    empresa_id: EmpresaDep,
    session: SesionDep,
    user: UsuarioDep,
) -> dict[str, Any]:
    """Fija el orden del conjunto completo.

    Un reordenado parcial no dice nada de donde va el destino ausente, y cualquier
    interpretacion deja el conjunto en un estado que el usuario no pidio y no sabe
    reproducir. Por eso el conjunto tiene que cuadrar exactamente; si no, 422.
    """
    try:
        return await fav.reordenar(
            session,
            empresa_id=empresa_id,
            usuario_id=user.id,
            ordenes=body.ordenes,
            actor=user.email,
            ip=request.client.host if request.client else None,
        )
    except NavigationError as exc:
        raise _error(exc) from exc


# ---------------------------------------------------------------------------
# US5 · Resúmenes de superficie
# ---------------------------------------------------------------------------


@resumenes_router.get(
    "/{superficie}",
    summary="Resumen de una superficie para el ejercicio activo",
    dependencies=[Depends(require_permission("acct", "ver"))],
)
async def obtener_resumen(
    superficie: str,
    request: Request,
    empresa_id: EmpresaDep,
    session: SesionDep,
) -> dict[str, Any]:
    """Cómo va esa área, en el ejercicio que el usuario tiene seleccionado.

    El guard es `acct:ver` como en el resto del shell: es un dato de lectura y los tres
    roles base lo tienen. Un usuario que solo puede consultar necesita saber cuántos
    asientos lleva el ejercicio; ocultárselo sería lo contrario de "ver".

    La cabecera `X-Ejercicio-Activa` se valida contra los ejercicios de **esta** empresa
    antes de resumir. Es el mismo filtro de pertenencia que usa `GET /contexto`, y por
    el mismo motivo: un ejercicio de otra empresa no puede convertirse en un resumen de
    esta, ni aunque la cabecera diga lo que quiera.

    La diferencia con el contexto es que aquí se admite un ejercicio **cerrado**, porque
    un resumen es una lectura y el estado final de un año cerrado es justamente lo que el
    usuario viene a mirar. La cabecera que gobierna la escritura sigue rechazándolo.
    """
    try:
        solicitado = validacion.parsear(request.headers.get("X-Ejercicio-Activa"))
        filas = await listar_ejercicios(session, empresa_id=empresa_id)
        validacion.validar_pertenencia(filas, solicitado)
        # El ejercicio pedido se respeta tal cual, sin pasar por `elegir_activo`. Ese
        # helper existe para decidir donde se ESCRIBE, y su regla 1 descarta lo que no
        # es seleccionable, es decir, lo cerrado. Aplicado aqui devolveria el resumen de
        # 2026 cuando se pide el de 2025 cerrado: un panel que responde con los datos de
        # otro ejercicio sin avisar, que es peor que un error.
        ejercicio = solicitado if solicitado is not None else elegir_activo(filas, None)
        return await resumenes.resumen(
            session, empresa_id=empresa_id, superficie=superficie, ejercicio=ejercicio
        )
    except NavigationError as exc:
        raise _error(exc) from exc
