"""Validacion de `X-Ejercicio-Activa` (SPEC-031, research D3).

La cabecera la envia el cliente, luego es **dato no confiable**, igual que
`X-Empresa-Activa`. Lo que la hace aceptable es que se valida contra la empresa de
la sesion antes de usarse.

POR QUE 422 Y NO 404: un 404 confirmaria al atacante que ese ejercicio existe en
otro tenant. La constitution III prohibe dar acceso a datos de otra empresa, y la
informacion de que un ano existe alli tambien es un dato. 422 dice "no es un
ejercicio valido para ti" sin confirmar nada.

POR QUE NO ES UNA FRONTERA DE TENANT: el ejercicio no filtra empresas, las
selecciona el contexto. `empresa_id` lo pone siempre `get_empresa_id` desde la
sesion; esta cabecera solo acota **que ejercicio** dentro de una empresa que el
usuario ya tiene. Por eso conviven sin que ninguna invalide a la otra: se resuelve
la empresa primero y el ejercicio despues.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession

from services.navigation.contexto import (
    CERRADO,
    EjercicioResuelto,
    elegir_activo,
    listar_ejercicios,
)

#: Rango aceptado en la cabecera. Un ano de cuatro digitas, ni mas ni menos: no tiene
#: sentido validar mas aqui porque el servicio que resuelve ya lo hace.
ANIO_MIN = 1900
ANIO_MAX = 2999

#: Subcadena de la cabecera, para mensajes de error.
DETALLE_NO_NUMERICO = "El ejercicio indicado no es un ano valido."
DETALLE_FUERA_DE_RANGO = "El ejercicio indicado esta fuera de rango."
DETALLE_DESCONOCIDO = "El ejercicio indicado no pertenece a la empresa activa."


def parsear(raw: str | None) -> int | None:
    """Interpreta la cabecera. `None` si no viene, que es un caso legitimo.

    Un valor presente pero mal formado es un error del cliente, no un ausente: se
    distingue a proposito, porque "no has enviado nada" y "has enviado basura" no
    merecen la misma respuesta.
    """
    if raw is None:
        return None
    limpio = raw.strip()
    if not limpio:
        return None
    try:
        anio = int(limpio)
    except (TypeError, ValueError) as exc:
        raise _no_numerico() from exc
    if not ANIO_MIN <= anio <= ANIO_MAX:
        raise _fuera_de_rango()
    return anio


def _no_numerico() -> Exception:
    from services.navigation.errores import error

    return error("ejercicio_invalido", DETALLE_NO_NUMERICO)


def _fuera_de_rango() -> Exception:
    from services.navigation.errores import error

    return error("ejercicio_invalido", DETALLE_FUERA_DE_RANGO)


def no_pertenece(ejercicio: int) -> Exception:
    """Error de un ejercicio que existe pero no es de esta empresa, o esta cerrado."""
    from services.navigation.errores import error

    return error("ejercicio_no_pertenece_a_empresa", DETALLE_DESCONOCIDO)


def cerrar(ejercicio: int) -> Exception:
    """Error de escritura sobre un ejercicio cerrado (FR-018)."""
    from services.navigation.errores import error

    return error(
        "ejercicio_cerrado",
        f"El ejercicio {ejercicio} esta cerrado y no admite asientos.",
    )


def validar_pertenencia(filas: list[EjercicioResuelto], solicitado: int | None) -> int | None:
    """Comprueba que el ejercicio pedido sea **de esta empresa**, y nada mas.

    Es `validar_solicitado` sin la regla de escritura, y esa diferencia es deliberada.

    `validar_solicitado` rechaza un ejercicio **cerrado** porque activar uno no tiene
    sentido: la cabecera `X-Ejercicio-Activa` gobierna por donde se **escribe**, y en un
    ejercicio cerrado no se escribe. Pero un **resumen** es una lectura, y "¿como
    termino el ejercicio cerrado?" es una pregunta que el usuario tiene todo el derecho
    a hacer, todos los cierres. Aplicar la regla de escritura a una lectura dejaria el
    panel sin poder mostrar el ultimo estado de un año ya cerrado, que es justo cuando
    más interesa verlo.

    Aqui la comprobacion es solo que el ejercicio **este en la lista**, y ya esta es la
    prueba de pertenencia: `listar_ejercicios` devuelve la union de `EjercicioContable` y
    `FiscalYear` **de esta empresa y solo de esta**, asi que estar en ella es ser suyo.
    No se mira `es_seleccionable` porque ese campo ya lleva dentro la regla de escritura
    (`estado != CERRADO`): usarlo aquí seria volver a meter por la puerta de atrás la
    regla que esta función existe para no aplicar.

    Lo de la pertenencia al tenant no cambia, y por eso el error es el mismo: un año de
    otra empresa y un año inexistente siguen siendo indistinguibles para quien pregunta.

    `solicitado is None` devuelve `None`, igual que la otra: quien llama decide el
    defecto.
    """
    if solicitado is None:
        return None
    if solicitado not in {f["ejercicio"] for f in filas}:
        raise no_pertenece(solicitado)
    return solicitado


def validar_solicitado(
    filas: list[EjercicioResuelto], solicitado: int | None
) -> int | None:
    """Comprueba que el ejercicio pedido sea utilizable en esta empresa.

    Se rechazan los dos casos por la misma razon y con el mismo codigo, a proposito:
    un ejercicio que no existe y uno que pertenece a otra empresa son
    indistinguibles para quien pregunta, y distinguirlos confirmaria informacion del
    otro tenant. Un ejercicio **cerrado** tambien se rechaza aqui, porque
    seleccionarlo para escribir no tiene sentido; el endpoint de contexto lo
    devuelve en la lista para que el usuario lo vea, pero no lo deja activo.
    """
    if solicitado is None:
        return None
    por_anio = {f["ejercicio"]: f for f in filas}
    fila = por_anio.get(solicitado)
    if fila is None or fila["estado"] == CERRADO:
        raise no_pertenece(solicitado)
    if not fila["es_seleccionable"]:
        # Existe como ano de informes pero no como ejercicio contable: tampoco
        # admite asientos.
        raise no_pertenece(solicitado)
    return solicitado


async def filas_de_contexto(
    db: AsyncSession, *, empresa_id: int, hoy: dt.date | None = None
) -> list[EjercicioResuelto]:
    """Atajo al listado de ejercicios, para no repetir la firma en los endpoints."""
    return await listar_ejercicios(db, empresa_id=empresa_id, hoy=hoy)


def es_utilizable(ejercicio: int, filas: list[EjercicioResuelto]) -> bool:
    """`True` si ese ejercicio existe en la empresa y admite asientos."""
    fila = next((f for f in filas if f["ejercicio"] == ejercicio), None)
    return bool(fila is not None and fila["es_seleccionable"])


def elegir_del_contexto(
    filas: list[EjercicioResuelto],
    *,
    cabecera: int | None,
    query: int | None,
    hoy: dt.date | None = None,
) -> int | None:
    """Resuelve que ejercicio se usa, aplicando la precedencia de FR-007.

    EL ORDEN IMPORTA Y ES EL MOTIVO DE QUE ESTA FUNCION EXISTA:

    1. **La URL manda sobre la cabecera.** Un `?ejercicio=2025` explicito gana
       siempre. Sin esta regla, abrir `/libros-iva?ejercicio=2025` escribiria en
       2026 porque la cabecera dijera 2026, y el apunte caeria en el ejercicio
       equivocado sin que nada lo dijera. Es el peor fallo posible de la feature.
    2. **Ninguna de las dos puede caer al valor por defecto si es invalida.** Un
       `?ejercicio=1999` falla en vez de resolverse al año de la cabecera. Caer seria
       peor que el fallo: el usuario cree que esta en 1999 y en realidad esta en otro,
       y el apunte entra sin que nada lo advierta.
    3. **La cabecera se valida aunque la query sea valida.** Si hay algo que
       rechazar, se rechaza. Aceptar la query y tirar la cabecera dejaria un estado
       ambiguo del que nadie sabria responder.
    4. **Sin ninguna de las dos, el año en curso** (CHK007), no "el mas reciente que
       exista": el caso que motiva la feature es contabilizar en dos ejercicios a la
       vez, y si el anterior fuese siempre el activo, el 31 de diciembre se estaria
       en el equivocado.

    Devuelve `None` solo si la empresa no tiene ningun ejercicio utilizable, que es
    el caso que la capa de API comunica en vez de asumir uno.
    """
    elegido = query if query is not None else cabecera
    if elegido is not None:
        validar_solicitado(filas, elegido)
        return elegido
    return elegir_activo(filas, None, hoy=hoy)
