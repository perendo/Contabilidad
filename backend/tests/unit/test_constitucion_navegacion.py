"""La feature de navegación cumple la constitución (SPEC-031, T059).

No reescribe los principios: los comprueba sobre el código de esta feature. Cada test
corresponde a un principio, y el motivo está en el nombre.

Lo que más importa aquí no es lo que se comprueba, sino **lo que no se comprueba**: los
cinco principios de la constitución hablan de contabilidad y esta feature no toca ni un
asiento. Se elige el ángulo que sí aplica —aislamiento de tenant, ausencia de `float` en
importes, escritura con auditoría, ACID, control de acceso por permiso— porque son las
partes que un módulo de navegación puede incumplir sin que nadie se dé cuenta.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
BACKEND = RAIZ / "backend" / "src" / "services" / "navigation"
API = RAIZ / "backend" / "src" / "api" / "navigation.py"
MIGRACION = RAIZ / "backend" / "migrations" / "022_favoritos.sql"


def _fuentes() -> list[Path]:
    return sorted(BACKEND.glob("*.py"))


# ---------------------------------------------------------------------------
# III · Multi-tenancy estricto
# ---------------------------------------------------------------------------


def test_ningun_metodo_toma_la_empresa_del_cliente() -> None:
    """`empresa_id` es siempre un parámetro de la llamada, nunca un valor del body o el path.

    Es la forma que permite que el filtro se lea de un vistazo: si `empresa_id` aparece en
    la firma de todos los servicios, es que ninguno de ellos puede haberlo tomado de la
    entrada del usuario.
    """
    for ruta in _fuentes():
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for funcion in ast.walk(arbol):
            if not isinstance(funcion, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            args = [a.arg for a in funcion.args.args + funcion.args.kwonlyargs]
            if "empresa_id" in args:
                continue
            # Un servicio que toca datos por tenant tiene que pedir la empresa. Se listan
            # los que no lo hacen para que la lista sea corta y revisable.
            if funcion.name.startswith(("_", "validar", "es_", "parsear", "normalizar")):
                continue
            cuerpo = ast.dump(funcion)
            if "SELECT" in cuerpo or "select(" in cuerpo or "db." in cuerpo:
                raise AssertionError(
                    f"{ruta.name}:{funcion.name} consulta la base sin pedir empresa_id"
                )


def test_el_ruta_de_lectura_no_acepta_empresa_por_parametro() -> None:
    """La empresa sale siempre de la sesión, en las cuatro rutas de la feature.

    Se comprueba que cada router declara el alias `EmpresaDep` **y** que ningún endpoint
    acepta `empresa_id` por query o por body. Un `empresa_id` opcional en el query string
    sería una puerta por la que un cliente podría pedir los datos de otra empresa.
    """
    texto = API.read_text(encoding="utf-8")

    # El alias se declara una vez a nivel de módulo.
    assert 'EmpresaDep = Annotated[int, Depends(get_empresa_id)]' in texto

    # Y lo usan los cuatro endpoints. Se cuentan los parámetros anotados con `EmpresaDep`.
    firmas = re.findall(r"(\w+):\s*EmpresaDep", texto)
    assert len(firmas) >= 4, f"solo {len(firmas)} endpoints reciben la empresa: {firmas}"

    # Ninguno acepta la empresa por query string ni por cuerpo.
    assert "empresa_id: int | None = None" not in texto
    assert not re.search(r"empresa_id:\s*int\s*\|\s*None", texto)
    # Y ningún schema de entrada lleva un campo `empresa_id`.
    for nombre in ("MarcarFavoritoBody", "ReordenarFavoritosBody"):
        i = texto.index(f"class {nombre}")
        bloque = texto[i : i + 700].split("\n\n\n")[0]
        assert "empresa_id" not in bloque, f"{nombre} acepta la empresa del cliente"


def test_los_cuatro_endpoints_derivan_la_empresa_por_el_alias() -> None:
    """Contexto, favoritos (tres verbos) y resúmenes: cinco endpoints, cinco usos.

    Se cuenta el uso del alias en vez de contar `Depends(get_empresa_id)`, porque el
    `Depends` aparece **una** vez a nivel de módulo: contar sus apariciones daría 1 y el
    test affirmaría algo falso.
    """
    texto = API.read_text(encoding="utf-8")
    assert len(re.findall(r"(\w+):\s*EmpresaDep", texto)) >= 5


# ---------------------------------------------------------------------------
# Regla fiscal · nada de float para dinero
# ---------------------------------------------------------------------------


def test_ningun_modulo_de_navegacion_anota_float() -> None:
    """`Decimal` para importes, `NUMERIC` en la base. Nunca `float`.

    El único `float` admisible sería el de la constante `CORTE_COMPACTO` del frontend, que
    son píxeles, no dinero. Aquí, en Python, no debe aparecer ninguno.
    """
    for ruta in _fuentes():
        texto = ruta.read_text(encoding="utf-8")
        assert "float" not in texto, f"{ruta.name} menciona float"


def test_los_importes_del_resumen_seuemiten_como_texto_cuatro_decimales() -> None:
    """Un `Decimal` serializado sin más puede llegar como `100.0` o como `1E+3`.

    El saldo de tesorería se devuelve como texto con cuatro decimales, que es la
    convención del repo. Un número en notación científica en un panel es un bug de
    presentación que la constitution no cubre pero el usuario sí ve.
    """
    texto = (BACKEND / "resumenes.py").read_text(encoding="utf-8")
    assert 'Decimal("0.0001")' in texto
    assert "ROUND_HALF_EVEN" in texto
    assert 'str(saldo)' in texto, "el importe sale como texto, no como float"


# ---------------------------------------------------------------------------
# II · Inmutabilidad y auditoría de la escritura
# ---------------------------------------------------------------------------


def test_toda_escritura_de_favoritos_se_audita() -> None:
    """Las tres operaciones de escritura pasan por `registrar_auditoria`.

    Marcar, desmarcar y reordenar. Un `DELETE` de favorito es la única cosa que se borra
    en la feature, y por eso es la que más conviene dejar rastro de quién lo hizo.
    """
    texto = (BACKEND / "favoritos.py").read_text(encoding="utf-8")
    for operacion in ("FAVORITO_MARCAR", "FAVORITO_DESMARCAR", "FAVORITO_REORDENAR"):
        assert operacion in texto, f"falta auditar {operacion}"
    assert texto.count("registrar_auditoria(") == 3, "una llamada por cada escritura"


def test_el_resumen_no_escribe_nada() -> None:
    """El resumen solo cuenta. Si un día escribiera, dejaría de ser una lectura.

    Es la garantía de que añadir el panel de cada superficie no ha metido escrituras en
    el camino de navegación: entrar en una pantalla no puede crear nada.
    """
    texto = (BACKEND / "resumenes.py").read_text(encoding="utf-8")
    for prohibido in ("session.add", "db.add", "registrar_auditoria", "insert("):
        assert prohibido not in texto, f"el resumen no puede escribir: {prohibido}"


# ---------------------------------------------------------------------------
# Transacciones · el boundary es `get_db`
# ---------------------------------------------------------------------------


def test_ningun_servicio_abre_su_propia_transaccion() -> None:
    """Ni `async with session.begin()` ni `commit()`.

    El boundary ACID es el generador de sesión de la capa de datos (constitución 1.0.1).
    Un servicio que abre su propia transacción rompe la atomicidad con la operación que
    lo invoca, que es justo lo que la enmienda de la constitución advertía.
    """
    for ruta in _fuentes():
        texto = ruta.read_text(encoding="utf-8")
        assert "session.begin()" not in texto, f"{ruta.name} abre su propia transaccion"
        assert "await db.commit()" not in texto, f"{ruta.name} hace commit: el commit es del boundary"
        assert "await session.commit()" not in texto, f"{ruta.name} hace commit"


def test_los_servicios_hacen_flush_y_no_commit() -> None:
    """`flush()` sí, porque pone lo escrito a disposición de la base sin cerrar nada."""
    texto = (BACKEND / "favoritos.py").read_text(encoding="utf-8")
    assert "flush()" in texto


# ---------------------------------------------------------------------------
# V · Pruebas obligatorias
# ---------------------------------------------------------------------------


def test_la_migracion_declara_el_uniquede_tres_columnas() -> None:
    """`UNIQUE (empresa_id, usuario_id, destino)`: el favorito es por persona y empresa.

    Con un UNIQUE más estrecho, dos personas en la misma empresa no podrían tener el
    mismo destino en favoritos, que es el uso normal.
    """
    texto = MIGRACION.read_text(encoding="utf-8")
    assert "UNIQUE (empresa_id, usuario_id, destino)" in texto
    assert "UNIQUE (empresa_id, id)" in texto


def test_la_migracion_rechaza_un_favorito_su_vinculo() -> None:
    """La FK a `user_companies` hace que un favorito sin vínculo sea **inválido**, no invisible.

    Es constitution III a nivel de esquema: el dato no puede existir en un estado
    prohibido, ni siquiera si alguien inserta a mano saltándose el servicio.
    """
    texto = MIGRACION.read_text(encoding="utf-8")
    assert "FOREIGN KEY (usuario_id, empresa_id)" in texto
    assert "user_companies (user_id, company_id)" in texto
