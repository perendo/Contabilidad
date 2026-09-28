"""Resúmenes de superficie, no vacíos y aislados (SPEC-031, US5, T046).

Por qué un endpoint de resúmenes y no composición en el cliente
--------------------------------------------------------------

Podría haberse resuelto desde el frontend, llamando a las APIs que ya existen. Se
descartó por dos razones, y las dos importan:

1. **El shell pediría entre cinco y seis peticiones en cada cambio de superficie**, cada
   una con su propio manejo de error. Un error en una dejaría un hueco en el panel
   mientras las demás llegan, y la interfaz no podría distinguir "no hay datos" de "la
   consulta falló".
2. **El aislamiento por empresa quedaría sin probar en un solo sitio.** Cada endpoint
   existente ya tiene sus tests de tenant, pero "cada uno aísla bien" no es lo mismo que
   "la vista que junta varios de esos endpoints aísla bien". La composición es donde un
   forgotten de filtro se convierte en una fuga: es el punto donde los datos de la
   empresa B entran en la pantalla de la A.

Nada de esto contradice el contrato, que no lo menciona: es una pieza que US5 necesita
y que el contrato no recogió. Queda anotado en el "Estado real" de `tasks.md`.

El resumen NO es un dato contable nuevo
---------------------------------------

Cada cifra viene de una tabla que ya existe y que ya está auditada y validada. Aquí solo
se cuenta. El resumen es de lectura y no crea ningún requisito nuevo sobre el
contabilizable, que es lo que lo mantiene dentro del alcance de la feature.
"""

from __future__ import annotations

import pytest

RUTA = "/api/v1/resumenes"
SUPERFICIES = ("contabilidad", "facturacion", "tesoreria", "informes", "fiscal", "maestros")


def _cuerpo(respuesta) -> dict:
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


@pytest.mark.parametrize("superficie", SUPERFICIES)
def test_cada_superficie_tiene_resumen_no_vacio(navegacion_client, superficie: str) -> None:
    """Las seis superficies responden y con contenido.

    Se comprueba el contenido y no solo el 200: un resumen que devuelve `{}` o una lista
    de ceros para siempre es un panel vacío que ocupa sitio y no informa de nada. Un
    conteo en cero **es** un dato válido, así que la prueba es que hay al menos una
    métrica con nombre, y no que los números sean distintos de cero.
    """
    cuerpo = _cuerpo(navegacion_client.get(f"{RUTA}/{superficie}", ejercicio=2026))

    assert cuerpo["superficie"] == superficie
    assert cuerpo["ejercicio"] == 2026, "el resumen es del ejercicio pedido"
    assert cuerpo["metricas"], "un resumen sin metricas no informa de nada"
    for metrica in cuerpo["metricas"]:
        assert metrica["etiqueta"], "una metrica sin etiqueta no se puede mostrar"
        assert metrica["valor"] is not None
    assert cuerpo["enlaces"], "el resumen debe decir a donde ir a actuar sobre el"


def test_el_resumen_de_contabilidad_cuenta_asientos_del_ejercicio(navegacion_client) -> None:
    """Cuentra por `ejercicio`, no por rango de fechas.

    Es el mismo criterio que usa `GET /contexto` y por el mismo motivo: el ejercicio es
    lo que el usuario ha seleccionado arriba, y contar por fechas daría un número que no
    corresponde a lo que ve en pantalla. La fixture de navegación siembra 2 asientos en
    2026 y 1 en 2025, así que la separación es comprobable.
    """
    de_2026 = _cuerpo(navegacion_client.get(f"{RUTA}/contabilidad", ejercicio=2026))
    de_2025 = _cuerpo(navegacion_client.get(f"{RUTA}/contabilidad", ejercicio=2025))
    assert de_2026["metricas"][0]["valor"] == 2, "los 2 asientos de 2026"
    assert de_2025["metricas"][0]["valor"] == 1, "el asiento de 2025 va a su ejercicio"

    # Y con 2025 cerrado, que es lo que tiene la fixture en esa empresa.
    cerrado = _cuerpo(navegacion_client.get(f"{RUTA}/contabilidad", ejercicio=2025))
    assert any(m["etiqueta"] == "Último asiento" for m in cerrado["metricas"])


def test_cada_empresa_ve_su_propio_resumen(navegacion_client) -> None:
    """El resumen de la empresa A no incluye datos de la B.

    Es la razón de existir de este endpoint, y la razón de este fichero. La empresa 20
    tiene un conjunto de datos DISTINTO y más pequeño que la 10, así que un fallo de
    filtro se ve en el número y no en un detalle pasajero.
    """
    de_a = _cuerpo(navegacion_client.get(f"{RUTA}/contabilidad", empresa_id=10, ejercicio=2026))
    de_b = _cuerpo(navegacion_client.get(f"{RUTA}/contabilidad", empresa_id=20, ejercicio=2026))

    assert de_a["empresa_id"] == 10
    assert de_b["empresa_id"] == 20
    # La A tiene 2 asientos de 2026 y la B tiene 1. Si el filtro fallara, los dos
    # resúmenes darían el mismo número.
    valor = lambda c: next(m["valor"] for m in c["metricas"] if m["clave"] == "asientos")
    assert valor(de_a) == 2
    assert valor(de_b) == 1, "el resumen de B no puede traer los asientos de A"


def test_ninguna_superficie_trae_datos_de_otra_empresa(navegacion_client) -> None:
    """Las seis superficies aíslan, no solo Contabilidad.

    Es la diferencia entre probar un caso y probar un mecanismo. Si una superficie
    aceptara el `empresa_id` del body en vez del de sesión, bastaría una para filtrar.
    """
    for superficie in SUPERFICIES:
        de_a = _cuerpo(navegacion_client.get(f"{RUTA}/{superficie}", empresa_id=10, ejercicio=2026))
        de_b = _cuerpo(navegacion_client.get(f"{RUTA}/{superficie}", empresa_id=20, ejercicio=2026))
        assert de_a["empresa_id"] == 10, superficie
        assert de_b["empresa_id"] == 20, superficie


def test_el_ejercicio_que_no_es_de_la_empresa_se_rechaza(navegacion_client) -> None:
    """La cabecera se valida contra los ejercicios de ESA empresa.

    Con la empresa 20, que solo tiene 2026, pedir 2025 es un error. No se resuelve en
    silencio ni se devuelve el resumen de otro ejercicio: sería el mismo fallo de
    aislamiento que filtrar mal, pero lanzado por la cabecera.
    """
    r = navegacion_client.get(f"{RUTA}/contabilidad", empresa_id=20, ejercicio=2025)
    assert r.status_code in (400, 422), r.text
    assert r.json()["detail"]["code"] == "ejercicio_no_pertenece_a_empresa"


def test_el_resumen_admite_un_ejercicio_cerrado(navegacion_client) -> None:
    """Un año cerrado se puede consultar, y devuelve SUS datos.

    Es la diferencia entre `validar_pertenencia` y `validar_solicitado`, y merece un
    test propio porque las dos reglas parecen la misma y no lo son. La de escritura
    rechaza un ejercicio cerrado porque la cabecera `X-Ejercicio-Activa` gobierna por
    donde se **escribe**. Un resumen es una **lectura**, y "¿cómo terminó el año que
    acabo de cerrar?" es la pregunta más natural que se le puede hacer a un cierre.

    Con la regla de escritura, este resumen daría los números de 2026 con el rótulo de
    2025, que es peor que un error: el usuario cierra el año y ve un año que no es el
    suyo, sin ningún aviso.
    """
    r = navegacion_client.get(f"{RUTA}/contabilidad", ejercicio=2025)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["ejercicio"] == 2025, "el rótulo tiene que ser el del año pedido"
    valor = next(m["valor"] for m in cuerpo["metricas"] if m["clave"] == "asientos")
    assert valor == 1, "los datos son los de 2025, no los de otro ejercicio"


def test_el_contexto_sigue_rechazando_el_ejercicio_cerrado(navegacion_client) -> None:
    """La regla de escritura no se ha relajado: `GET /contexto` sigue rechazándolo.

    Es la contraprueba del test anterior. Si `validar_pertenencia` hubiera contaminado
    `validar_solicitado`, los dos pasarían y el shell activaría un ejercicio cerrado,
    que es la vía por la que se acabaría escribiendo en un año cerrado (FR-018).
    """
    r = navegacion_client.get("/api/v1/contexto", ejercicio=2025)
    assert r.status_code in (400, 422), r.text
    assert r.json()["detail"]["code"] == "ejercicio_no_pertenece_a_empresa"


def test_sin_ejercicio_usa_el_activo(navegacion_client) -> None:
    """Sin cabecera, se resume el ejercicio activo, que es el que ve el usuario arriba."""
    cuerpo = _cuerpo(navegacion_client.get(f"{RUTA}/contabilidad"))
    assert cuerpo["ejercicio"] == 2026, "el año en curso en la fixture"


def test_una_empresa_sin_ejercicio_abre_igual_su_landing(navegacion_client) -> None:
    """Sin ningún ejercicio, la landing responde 200 y lo dice. No es un error.

    Es el caso de la empresa recién creada, y es el primer arranque de cualquiera. Si
    esto fuera un 422, la primera pantalla que vería un usuario nuevo sería un error, y
    no podría ni crear el ejercicio porque la aplicación ya le está diciendo que no hay
    ninguno. Por eso se devuelve `motivo: sin_ejercicio` con cero métricas, y la interfaz
    lo explica.

    La empresa 40 no tiene `EjercicioContable` ni `FiscalYear`: es exactamente ese caso.
    Se emite un token propio para ella, porque el guard `get_empresa_id` exige una
    relación activa y el usuario del fixture solo está vinculado a la 10 y a la 20. Un
    403 aquí sería el guard funcionando, no un fallo del resumen.
    """
    token = _crear_empresa_sin_ejercicios(navegacion_client, 40)
    r = navegacion_client.get(f"{RUTA}/contabilidad", empresa_id=40, token_key=token)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["ejercicio"] is None
    assert cuerpo["motivo"] == "sin_ejercicio"
    assert cuerpo["metricas"] == [], "sin ejercicio no hay cifras que inventar"
    assert cuerpo["empresa_id"] == 40


def _crear_empresa_sin_ejercicios(navegacion_client, empresa: int) -> str:
    """Empresa con su ADMIN y sin ejercicios. Devuelve el token para poder entrar."""
    from models.iam.user import User
    from models.iam.user_company import UserCompany, UserRol
    from services.auth.security import emit_token, hash_password
    from tests.conftest import crear_empresa

    usuario = 400 + empresa - 40

    async def _sembrar(session):
        # Con `crear_empresa` de conftest, y no construyendo la fila a mano: el guard de
        # siembra (`test_guard_siembra_empresa.py`) convierte eso en un fallo de suite,
        # porque el NIF y la razón social se derivan del identificador.
        await crear_empresa(session, empresa)
        session.add(
            User(id=usuario, email=f"s{empresa}@pg.es", password_hash=hash_password("pw"), full_name="Sin Ejercicio")
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

    navegacion_client.run(navegacion_client.mutar(_sembrar))
    return emit_token(usuario)


def test_una_superficie_inexistente_es_404(navegacion_client) -> None:
    r = navegacion_client.get(f"{RUTA}/inventada")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "superficie_desconocida"


def test_sin_autenticacion_no_hay_resumen(navegacion_client) -> None:
    assert navegacion_client.client.get(f"{RUTA}/contabilidad").status_code == 401


def test_read_only_puede_leer_el_resumen(navegacion_client) -> None:
    """El resumen es de lectura, y `acct:ver` lo poseen los tres roles base.

    READ_ONLY tiene que verlo: un usuario que solo puede consultar necesita saber
    cuántos asientos tiene, y ocultarle el resumen por su rol sería lo contrario
    de "ver".
    """
    r = navegacion_client.get(f"{RUTA}/contabilidad", token_key="readonly", ejercicio=2026)
    assert r.status_code == 200, r.text
    assert r.json()["metricas"]
