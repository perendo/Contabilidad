"""El p95 de `GET /api/v1/contexto` con volumen (SPEC-031, T069, T065).

La zona de contexto se pinta en **todas** las pantallas, y a cada cambio de empresa o de
ejercicio. Si seanca la pantalla, su latencia es la latencia de la aplicación. Por eso
esta medición existe: no para demostrar que va rápido, sino para tener un número al que
comparar cuando algo se degrade.

QUÉ MIDE Y QUÉ NO
-----------------

Mide el p95, no la media. En una ruta que se llama en cada pantalla, lo que se nota es la
cola: si el 95 por ciento va bien y el último por ciento tarda dos segundos, el usuario
con una cuenta lenta nota un parpadeo en cada navegación. La media escondería justo eso.

No mide el p99 ni el máximo, porque con el volumen de un test esos valores son ruido: una
pausa del recolector de basura en el proceso de test se parecería a un problema de
rendimiento y no lo es. Con 5.000 asientos repartidos en dos ejercicios y cinco
mediciones, el p95 es la cifra que se puede defender.

Es una medición, no un requisito con un umbral. `P95_MAXIMO_MS` está ahí para que un
camino tres veces más lento que hoy salga en rojo, y no para marcar un objetivo que
depende de la máquina en la que corre.
"""

from __future__ import annotations

import datetime as dt
import os
import statistics
import time
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from models.acct.journal import JournalEntry, JournalEntryLine, JournalEntryTipo
from tests.conftest import crear_empresa

#: Ejercicios en los que se reparte el volumen. Dos, porque el caso interesante es tener
#: que elegir y que el listado de ejercicios traiga ambos.
EJERCICIOS = (2025, 2026)

#: Asientos por ejercicio. 5.000 en total.
POR_EJERCICIO = 2_500

#: Muestra de peticiones. Cinco es poco para un p95 y es lo que hace el test rápido:
#: mide la forma de la distribución, no la línea.
MEDICIONES = 5

#: Se dispara solo con `PERF_NAV=1`. Por defecto el test se salta, porque insertar 5.000
#: asientos cuesta más que todo el resto de la suite de navegación junta y no falla
#: cuando la aplicación va bien: solo informa.
ACTIVO = os.environ.get("PERF_NAV", "0") == "1"


def _activo(request: pytest.FixtureRequest) -> bool:
    """Si esta medición debe correr.

    Opt-in por dos motivos, y el primero manda sobre el segundo: insertar 5.000 asientos
    cuesta más que toda la suite de navegación junta, y la medición **no falla** cuando
    la aplicación va bien, solo informa. Meterla en la suite diaria avisaría de algo que
    aún no ha pasado y enseñaría a ignorar el resto de avisos.
    """
    return bool(request.config.getoption("--perf-nav", default=ACTIVO))


#: Techo de aviso, muy por encima de lo medido hoy. Es un detector de regresión, no un
#: objetivo: si esto salta, hay que mirar qué cambió antes de culpar al código nuevo.
P95_MAXIMO_MS = 750


async def _sembrar_base(session: AsyncSession, empresa: int, usuario: int) -> None:
    """Empresa con su ADMIN y la matriz de permisos, en el motor del fixture HTTP.

    Sin el vínculo, `get_empresa_id` responde 403; sin la matriz, `require_permission`
    responde 403 por otra razón. Los dos fallos se parecen y son cosas distintas, así que
    se siembra el camino completo: es lo que hace la aplicación al dar de alta una
    empresa, y medir eso es medir la realidad y no un caso aparte.
    """
    from models.iam.user import User
    from models.iam.user_company import UserCompany, UserRol
    from services.auth.security import hash_password
    from services.security.catalogo import sembrar_seguridad
    
    await crear_empresa(session, empresa)
    session.add(
        User(
            id=usuario,
            email=f"perf{empresa}@pg.es",
            password_hash=hash_password("pw"),
            full_name="Perf",
        )
    )
    session.add(
        UserCompany(
            id=usuario,
            user_id=usuario,
            company_id=empresa,
            role=UserRol.ADMIN,
            is_default=True,
        )
    )
    await session.flush()
    await sembrar_seguridad(session, empresa_id=empresa)
    await _sembrar_volumen(session, empresa)


async def _sembrar_volumen(session: AsyncSession, empresa: int) -> None:
    """5.000 asientos POSTED repartidos en dos ejercicios, con sus dos líneas.

    Las líneas importan: `contar_asientos` filtra por `journal_entry.ejercicio` y no toca
    las líneas, pero el resto de consultas del contexto sí las miran, y medir con asientos
    sin líneas daría un número de una aplicación que no existe.
    """
    filas = []
    for ejercicio in EJERCICIOS:
        # `fecha` es una columna Date: admite `datetime.date`, no una cadena. Pasarle un
        # texto funciona en PostgreSQL y falla en SQLite, y el fallo dice "only accepts
        # Python date objects", que es claro pero apunta al tipo equivocado.
        fecha = dt.date(ejercicio, 6, 15)
        for numero in range(1, POR_EJERCICIO + 1):
            entrada = uuid.uuid4()
            filas.append(
                JournalEntry(
                    id=entrada,
                    empresa_id=empresa,
                    ejercicio=ejercicio,
                    fecha=fecha,
                    tipo=JournalEntryTipo.GENERAL,
                    concepto=f"Asiento de volumen {numero}",
                    numero_asiento=numero,
                    estado="POSTED",
                )
            )
            filas.append(
                JournalEntryLine(
                    id=uuid.uuid4(),
                    empresa_id=empresa,
                    journal_entry_id=entrada,
                    cuenta="4300",
                    debe=100,
                    haber=0,
                )
            )
            filas.append(
                JournalEntryLine(
                    id=uuid.uuid4(),
                    empresa_id=empresa,
                    journal_entry_id=entrada,
                    cuenta="7000",
                    debe=0,
                    haber=100,
                )
            )
    session.add_all(filas)
    await session.flush()


def test_p95_del_contexto_con_volumen(
    navegacion_client,
    request,
) -> None:
    """Mide el p95 del contexto y lo deja escrito en la salida del test.

    Se salta salvo que se pida con `PERF_NAV=1`, por el coste de sembrar el volumen. El
    motivo está en el propio módulo: insertar 5.000 asientos en cada corrida haria la
    suite inútil para desarrollo.
    """
    if not _activo(request):
        pytest.skip("medicion de rendimiento: lanzar con PERF_NAV=1")

    empresa = 77
    # Se siembra en el motor del **propio** fixture HTTP, no en `db_session_factory`.
    # Cada uno tiene su SQLite en memoria, así que lo sembrado en el otro es invisible
    # para el cliente y el error es "Usuario inactivo o inexistente", que no dice que el
    # problema es de base de datos.
    #
    # La empresa se crea **sin** PGC a propósito, porque a este fixture no se le siembra
    # el plan de cuentas y `sembrar_empresa_pgc` intentaría insertar 82 cuentas contra
    # un árbol que no está. Lo que se mide es la latencia del contexto, y el contexto no
    # toca el plan de cuentas.
    navegacion_client.run(
        navegacion_client.mutar(
            lambda session: _sembrar_base(session, empresa, 770)
        )
    )

    tiempos = []
    token = navegacion_client.token_para_usuario(770)
    for _ in range(MEDICIONES):
        inicio = time.perf_counter()
        r = navegacion_client.get("/api/v1/contexto", empresa_id=empresa, token_key=token)
        tiempos.append((time.perf_counter() - inicio) * 1000)
        assert r.status_code == 200, r.text
        cuerpo = r.json()
        # El contexto tiene que traer los dos ejercicios: con volumen, el filtro por
        # empresa es lo único que impide que aparezcan los de otra tenant.
        assert {e["ejercicio"] for e in cuerpo["ejercicios"]} <= set(EJERCICIOS)

    p95 = statistics.quantiles(tiempos, n=100, method="inclusive")[94]
    print(
        f"\n  GET /contexto con {POR_EJERCICIO * 2} asientos: "
        f"min {min(tiempos):.1f} ms · mediana {statistics.median(tiempos):.1f} ms · "
        f"p95 {p95:.1f} ms"
    )
    assert p95 < P95_MAXIMO_MS, f"p95 de {p95:.0f} ms, por encima del aviso de {P95_MAXIMO_MS} ms"
