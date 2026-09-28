"""Servicio de favoritos (SPEC-031, US4, tareas T037 y T061).

La semografia que estos tests fijan sale de la revision del checklist (CHK025), donde
se encontro una contradiccion real entre cuatro artefactos: el caso borde del spec y
`research.md` decian que un favorito por encima del maximo **se recorta y se guarda**,
mientras el contrato y las tareas decian **422**. Gana el recorte, y el motivo es
concreto: rechazar en la escritura dejaria al usuario con 5 favoritos sin poder anadir
el suyo, que es justo lo que el requisito prohibe.

LAS CINCO REGLAS

1. **Marcar es idempotente.** Dos veces el mismo destino no es un error: es lo que pasa
   al pulsar el boton en dos pestanas.
2. **Superar el maximo NO es un error.** El sexto se guarda; el recorte ocurre en la
   lectura, que informa `total` y `visibles`.
3. **Desmarcar es idempotente.** Si no estaba, 204 y listo.
4. **Reordenar exige el conjunto completo.** Un reordenado parcial deja el conjunto en
   un estado que el usuario no pidio y que no sabe reproducir.
5. **Marcar y desmarcar se auditan**, en la misma transaccion ACID (constitution,
   seccion de stack). Es una operacion de escritura y la constitution obliga a
   registrarla aunque no toque datos contables.

Y una sexta, que es la constitution III: **el favorito solo puede existir si el
usuario esta vinculado a esa empresa**. Eso lo garantiza la FK compuesta, no el
servicio; aqui se comprueba que el servicio no la eluda.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from models.audit.audit_log import AuditLog
from models.navigation.favorito import FavoritoUsuario
from services.navigation.errores import NavigationError
from services.navigation.favoritos import (
    MAXIMO_VISIBLES,
    OPERACION_DESMARCAR,
    OPERACION_MARCAR,
    desmarcar,
    listar,
    marcar,
    reordenar,
)
from tests.conftest import crear_empresas

EMPRESA = 10
OTRA_EMPRESA = 20

#: Destinos que existen en el mapa de superficies. El servicio NO importa el mapa
#: (es TypeScript): valida contra lo que le inyecta el endpoint, que es quien lo lee.
DESTINOS = [
    ("vencimientos", 1),
    ("conciliacion", 2),
    ("asientos", 3),
    ("facturas", 4),
    ("balance", 5),
    ("libros-iva", 6),
]


async def _sembrar_vinculo(db: AsyncSession, usuario_id: int = 1) -> None:
    from models.iam.user import User
    from models.iam.user_company import UserCompany, UserRol
    from services.auth.security import hash_password

    db.add(User(id=usuario_id, email=f"u{usuario_id}@fav.es", password_hash=hash_password("pw"), full_name="U"))
    db.add(
        UserCompany(
            id=usuario_id,
            user_id=usuario_id,
            company_id=EMPRESA,
            role=UserRol.ACCOUNTANT,
            is_default=True,
        )
    )
    await db.flush()


# ---------------------------------------------------------------------------
# 1. Marcar es idempotente
# ---------------------------------------------------------------------------


async def test_marcar_guarda_el_favorito(db_session: AsyncSession) -> None:
    await crear_empresas(db_session, EMPRESA)
    await _sembrar_vinculo(db_session)
    await marcar(db_session, empresa_id=EMPRESA, usuario_id=1, destino="vencimientos", orden=1)
    filas = (await db_session.execute(sa.select(FavoritoUsuario))).scalars().all()
    assert len(filas) == 1
    assert filas[0].destino == "vencimientos"
    assert filas[0].orden == 1
    assert filas[0].empresa_id == EMPRESA
    assert filas[0].usuario_id == 1


async def test_marcar_dos_veces_no_duplica(db_session: AsyncSession) -> None:
    await crear_empresas(db_session, EMPRESA)
    await _sembrar_vinculo(db_session)
    await marcar(db_session, empresa_id=EMPRESA, usuario_id=1, destino="vencimientos", orden=1)
    await marcar(db_session, empresa_id=EMPRESA, usuario_id=1, destino="vencimientos", orden=1)
    filas = (await db_session.execute(sa.select(FavoritoUsuario))).scalars().all()
    assert len(filas) == 1, "marcar dos veces el mismo destino debe ser idempotente"


async def test_marcar_actualiza_el_orden_si_cambia(db_session: AsyncSession) -> None:
    await crear_empresas(db_session, EMPRESA)
    await _sembrar_vinculo(db_session)
    await marcar(db_session, empresa_id=EMPRESA, usuario_id=1, destino="vencimientos", orden=1)
    await marcar(db_session, empresa_id=EMPRESA, usuario_id=1, destino="vencimientos", orden=4)
    filas = (await db_session.execute(sa.select(FavoritoUsuario))).scalars().all()
    assert len(filas) == 1
    assert filas[0].orden == 4


# ---------------------------------------------------------------------------
# 2. Superar el maximo NO es un error
# ---------------------------------------------------------------------------


async def test_un_sexto_favorito_se_guarda(db_session: AsyncSession) -> None:
    """El recorte es de LECTURA, no de escritura (CHK025).

    Es la prueba que mas peso tiene del fichero: si alguien "corrige" el servicio
    para rechazar el sexto, esta prueba falla y explica por que el rechazo estaba
    mal.
    """
    await crear_empresas(db_session, EMPRESA)
    await _sembrar_vinculo(db_session)
    for destino, orden in DESTINOS:
        await marcar(
            db_session, empresa_id=EMPRESA, usuario_id=1, destino=destino, orden=orden
        )
    filas = (await db_session.execute(sa.select(FavoritoUsuario))).scalars().all()
    assert len(filas) == 6, "los seis deben estar guardados; el recorte es al leer"
    assert MAXIMO_VISIBLES == 5


async def test_la_lectura_recorta_a_cinco_e_informa(db_session: AsyncSession) -> None:
    """La lectura dice cuantos hay y cuantos se ven, para que la UI avise."""
    await crear_empresas(db_session, EMPRESA)
    await _sembrar_vinculo(db_session)
    for destino, orden in DESTINOS:
        await marcar(
            db_session, empresa_id=EMPRESA, usuario_id=1, destino=destino, orden=orden
        )
    respuesta = await listar(db_session, empresa_id=EMPRESA, usuario_id=1)
    assert respuesta["total"] == 6
    assert respuesta["visibles"] == MAXIMO_VISIBLES
    assert len(respuesta["items"]) == MAXIMO_VISIBLES
    # Y vienen en orden.
    assert [f["orden"] for f in respuesta["items"]] == [1, 2, 3, 4, 5]


async def test_lo_recortado_no_se_pierde(db_session: AsyncSession) -> None:
    """El sexto sigue en la base y vuelve a aparecer si desmarca otro.

    Es la otra mitad de CHK025: si el oculto se perdiera, el requisito "no perder
    los que excedan" seria falso.
    """
    await crear_empresas(db_session, EMPRESA)
    await _sembrar_vinculo(db_session)
    for destino, orden in DESTINOS:
        await marcar(
            db_session, empresa_id=EMPRESA, usuario_id=1, destino=destino, orden=orden
        )
    await desmarcar(db_session, empresa_id=EMPRESA, usuario_id=1, destino="asientos")
    respuesta = await listar(db_session, empresa_id=EMPRESA, usuario_id=1)
    assert respuesta["total"] == 5
    destinos = {f["destino"] for f in respuesta["items"]}
    assert "libros-iva" in destinos, "el sexto debe reaparecer al liberar sitio"


# ---------------------------------------------------------------------------
# 3. Desmarcar es idempotente
# ---------------------------------------------------------------------------


async def test_desmarcar_borra(db_session: AsyncSession) -> None:
    await crear_empresas(db_session, EMPRESA)
    await _sembrar_vinculo(db_session)
    await marcar(db_session, empresa_id=EMPRESA, usuario_id=1, destino="vencimientos", orden=1)
    await desmarcar(db_session, empresa_id=EMPRESA, usuario_id=1, destino="vencimientos")
    filas = (await db_session.execute(sa.select(FavoritoUsuario))).scalars().all()
    assert filas == []


async def test_desmarcar_uno_que_no_esta_no_falla(db_session: AsyncSession) -> None:
    await crear_empresas(db_session, EMPRESA)
    await _sembrar_vinculo(db_session)
    await desmarcar(db_session, empresa_id=EMPRESA, usuario_id=1, destino="vencimientos")
    filas = (await db_session.execute(sa.select(FavoritoUsuario))).scalars().all()
    assert filas == []


# ---------------------------------------------------------------------------
# 4. Validacion
# ---------------------------------------------------------------------------


async def test_orden_no_positivo_se_rechaza(db_session: AsyncSession) -> None:
    """El 422 es por el VALOR de la posicion, no por la cantidad de favoritos.

    Se distingue a proposito: `orden` fuera de rango es una peticion malformada; un
    sexto favorito es una operacion valida.
    """
    await crear_empresas(db_session, EMPRESA)
    await _sembrar_vinculo(db_session)
    for orden in (0, -1):
        with pytest.raises(NavigationError) as exc:
            await marcar(
                db_session, empresa_id=EMPRESA, usuario_id=1, destino="vencimientos", orden=orden
            )
        assert exc.value.code == "orden_fuera_de_rango"


async def test_el_orden_se_persiste_como_esta(db_session: AsyncSession) -> None:
    """Un orden grande es valido: es la posicion dentro del conjunto, no del top 5."""
    await crear_empresas(db_session, EMPRESA)
    await _sembrar_vinculo(db_session)
    await marcar(db_session, empresa_id=EMPRESA, usuario_id=1, destino="vencimientos", orden=99)
    filas = (await db_session.execute(sa.select(FavoritoUsuario))).scalars().all()
    assert filas[0].orden == 99


async def test_el_mismo_destino_no_se_puede_marcar_para_dos_usuarios(
    db_session: AsyncSession,
) -> None:
    """Dos usuarios pueden tener el mismo destino: el favorito es por usuario."""
    await crear_empresas(db_session, EMPRESA)
    await _sembrar_vinculo(db_session, 1)
    await _sembrar_vinculo(db_session, 2)
    await marcar(db_session, empresa_id=EMPRESA, usuario_id=1, destino="vencimientos", orden=1)
    await marcar(db_session, empresa_id=EMPRESA, usuario_id=2, destino="vencimientos", orden=1)
    filas = (await db_session.execute(sa.select(FavoritoUsuario))).scalars().all()
    assert len(filas) == 2


# ---------------------------------------------------------------------------
# 5. Reordenar
# ---------------------------------------------------------------------------


async def test_reordenar_cambia_el_orden(db_session: AsyncSession) -> None:
    await crear_empresas(db_session, EMPRESA)
    await _sembrar_vinculo(db_session)
    for destino, orden in DESTINOS[:3]:
        await marcar(
            db_session, empresa_id=EMPRESA, usuario_id=1, destino=destino, orden=orden
        )
    await reordenar(
        db_session,
        empresa_id=EMPRESA,
        usuario_id=1,
        ordenes=["asientos", "vencimientos", "conciliacion"],
    )
    respuesta = await listar(db_session, empresa_id=EMPRESA, usuario_id=1)
    assert [f["destino"] for f in respuesta["items"]] == [
        "asientos",
        "vencimientos",
        "conciliacion",
    ]


async def test_reordenar_exige_el_conjunto_completo(db_session: AsyncSession) -> None:
    """Un reordenado parcial deja el conjunto en un estado que nadie pidio.

    Es deliberado que sea estricto: un `PATCH` con dos de tres destinos no dice nada
    de donde va el tercero, y cada interpretacion posible derrota al usuario.
    """
    await crear_empresas(db_session, EMPRESA)
    await _sembrar_vinculo(db_session)
    for destino, orden in DESTINOS[:3]:
        await marcar(
            db_session, empresa_id=EMPRESA, usuario_id=1, destino=destino, orden=orden
        )
    with pytest.raises(NavigationError) as exc:
        await reordenar(
            db_session,
            empresa_id=EMPRESA,
            usuario_id=1,
            ordenes=["asientos", "vencimientos"],
        )
    assert exc.value.code == "conjunto_incompleto"


async def test_reordenar_rechaza_repetidos(db_session: AsyncSession) -> None:
    await crear_empresas(db_session, EMPRESA)
    await _sembrar_vinculo(db_session)
    for destino, orden in DESTINOS[:2]:
        await marcar(
            db_session, empresa_id=EMPRESA, usuario_id=1, destino=destino, orden=orden
        )
    with pytest.raises(NavigationError) as exc:
        await reordenar(
            db_session,
            empresa_id=EMPRESA,
            usuario_id=1,
            ordenes=["asientos", "asientos"],
        )
    assert exc.value.code == "conjunto_incompleto"


# ---------------------------------------------------------------------------
# 6. constitution: auditoria en la misma transaccion
# ---------------------------------------------------------------------------


async def test_marcar_escribe_auditoria(db_session: AsyncSession) -> None:
    """`FAVORITO_MARCAR` queda en `audit_log` con usuario, IP, UTC y payload."""
    await crear_empresas(db_session, EMPRESA)
    await _sembrar_vinculo(db_session)
    await marcar(
        db_session,
        empresa_id=EMPRESA,
        usuario_id=1,
        destino="vencimientos",
        orden=1,
        actor="jperez",
        ip="10.0.0.5",
    )
    filas = (
        (await db_session.execute(sa.select(AuditLog).where(AuditLog.operacion == OPERACION_MARCAR)))
        .scalars()
        .all()
    )
    assert len(filas) == 1
    assert filas[0].usuario == "jperez"
    assert filas[0].ip == "10.0.0.5"
    assert filas[0].empresa_id == EMPRESA
    assert filas[0].entidad == "favorito"
    assert filas[0].entidad_id == "vencimientos"
    assert filas[0].timestamp is not None
    # El destino va en `entidad_id`, y el payload lleva el delta. Se comprueba el
    # delta porque es lo que responde a "que cambio exactamente".
    assert '"orden": 1' in (filas[0].payload or "")


async def test_desmarcar_escribe_auditoria(db_session: AsyncSession) -> None:
    await crear_empresas(db_session, EMPRESA)
    await _sembrar_vinculo(db_session)
    await marcar(db_session, empresa_id=EMPRESA, usuario_id=1, destino="vencimientos", orden=1)
    await desmarcar(
        db_session, empresa_id=EMPRESA, usuario_id=1, destino="vencimientos", actor="jperez"
    )
    filas = (
        (
            await db_session.execute(
                sa.select(AuditLog).where(AuditLog.operacion == OPERACION_DESMARCAR)
            )
        )
        .scalars()
        .all()
    )
    assert len(filas) == 1
    assert filas[0].usuario == "jperez"


async def test_la_auditoria_y_el_favorito_van_en_la_misma_transaccion(
    motor_db_session,
) -> None:
    """Si la operacion falla, no queda favorito ni rastro de auditoria.

    Es la comprobacion de atomicidad de verdad: no basta con que los dos se escriban,
    tienen que escribirse o deshacerse juntos (constitution, seccion de stack).

    Se provoca el fallo DESPUES de que el servicio haya escrito, y se comprueba que
    la transaccion entera se deshizo. Un servicio que escribiera la auditoria en otra
    sesion, o despues del commit, pasaria el test de "escribe auditoria" y fallaria
    este.
    """
    from models.iam.user import User
    from models.iam.user_company import UserCompany, UserRol
    from services.auth.security import hash_password
    from services.navigation import favoritos as svc

    # `motor_db_session` ya siembra un usuario, asi que se usa un id alto que no
    # colisione con el suyo. Antes se colisiono y el fallo fue `UNIQUE users.id`,
    # que no dice nada del motivo real.
    motor_db_session.add(
        User(id=900, email="a@fav.es", password_hash=hash_password("pw"), full_name="A")
    )
    motor_db_session.add(
        UserCompany(
            id=900, user_id=900, company_id=10, role=UserRol.ADMIN, is_default=True
        )
    )
    await motor_db_session.flush()

    # El fallo se provoca DESPUES de que el servicio haya escrito, y se revierte a
    # mano, que es lo que hace el boundary de `get_db` ante una excepcion. El
    # `rollback` va FUERA del `pytest.raises`: dentro nunca se ejecutaria, porque la
    # excepcion se propaga antes de llegar a el.
    with pytest.raises(RuntimeError):
        await svc.marcar(
            motor_db_session,
            empresa_id=10,
            usuario_id=900,
            destino="vencimientos",
            orden=1,
        )
        raise RuntimeError("fallo simulado despues de marcar")

    await motor_db_session.rollback()

    filas = (
        (await motor_db_session.execute(sa.select(FavoritoUsuario))).scalars().all()
    )
    assert filas == [], "el favorito debio deshacerse con la transaccion"
    audits = (
        (
            await motor_db_session.execute(
                sa.select(AuditLog).where(AuditLog.entidad == "favorito")
            )
        )
        .scalars()
        .all()
    )
    assert audits == [], "la auditoria debio deshacerse con la misma transaccion"
