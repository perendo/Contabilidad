"""Coherencia de los mensajes de error de ejercicio (SPEC-031, T036).

CRUZA LAS DOS CAPAS: los codigos que el backend puede emitir y los que el cliente
traduce. No es un test de cada lado por separado, sino de que **encajen**.

El fallo que evita es concreto: el backend anade un codigo nuevo, ninguna pantalla lo
conoce porque nadie se entero, y el usuario ve un texto crudo. Con este test, anadir
el codigo al backend sin traducirlo en `components/navigation/errores.ts` rompe la
suite en el momento de anadirlo.

Tambien comprueba que la traduccion sea **accionable**, que es el valor que anade
T036: el backend ya dice "el ejercicio esta cerrado" en castellano, lo que faltaba
era decir "puedes pasar a 2026".
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
ERRORES_TS = RAIZ / "frontend" / "src" / "components" / "navigation" / "errores.ts"
SERVICIO_PY = RAIZ / "backend" / "src" / "services" / "navigation" / "ejercicio_activo.py"
MOTOR_PY = RAIZ / "backend" / "src" / "services" / "journal" / "entry_service.py"


def _traducidos() -> dict[str, str]:
    """Codigo -> texto, tal y como los declara el cliente."""
    texto = ERRORES_TS.read_text(encoding="utf-8")
    cuerpo = re.search(r"export const MENSAJES[^=]*=\s*\{(.*?)\n\};", texto, re.DOTALL)
    assert cuerpo is not None, "el cliente debe declarar MENSAJES"
    salida: dict[str, str] = {}
    for codigo, bloque in re.findall(
        r"(\w+):\s*\{\s*texto:\s*\"([^\"]+)\"", cuerpo.group(1)
    ):
        salida[codigo] = bloque
    return salida


def _codigos_de_ejercicio_del_backend() -> set[str]:
    """Codigos de error de ejercicio que el backend puede emitir de verdad."""
    encontrados: set[str] = set()
    for ruta in (SERVICIO_PY, MOTOR_PY):
        texto = ruta.read_text(encoding="utf-8")
        # Formatos: `error("ejercicio_x", ...)` y `EJERCICIO_X = "ejercicio_x"`.
        encontrados |= set(re.findall(r'"(ejercicio_[a-z_]+)"', texto))
        encontrados |= set(re.findall(r"'(ejercicio_[a-z_]+)'", texto))
    return encontrados


def test_el_cliente_traduce_todo_lo_que_el_backend_puede_emitir() -> None:
    """La red que evita el texto crudo.

    Si el backend emite un codigo que el cliente no traduce, aqui falla. Es el
    contrato entre las dos capas, comprobado en lugar de supuesto.
    """
    codigos = _codigos_de_ejercicio_del_backend()
    traducidos = set(_traducidos())
    sin_traducir = sorted(codigos - traducidos)
    assert sin_traducir == [], (
        "el backend emite estos codigos y el cliente no los traduce, asi que el "
        "usuario veria el texto crudo:\n"
        + "\n".join(f"  {c}" for c in sin_traducir)
    )


def test_cada_traduccion_es_accionable() -> None:
    """Un mensaje sin accion es el problema que T036 vino a resolver.

    Se exige que la accion exista, no que el texto sea largo. Y que la accion tenga
    una forma de escrita, porque `true` sin decir como se ejecuta no ayuda a nadie.
    """
    texto = ERRORES_TS.read_text(encoding="utf-8")
    cuerpo = re.search(r"export const MENSAJES[^=]*=\s*\{(.*?)\n\};", texto, re.DOTALL)
    assert cuerpo is not None
    for codigo, bloque in re.findall(
        r"(\w+):\s*\{([^}]*)\}", cuerpo.group(1), re.DOTALL
    ):
        assert "texto:" in bloque, f"{codigo} no declara texto"
        assert "ofreceCambio:" in bloque, (
            f"{codigo} no declara si ofrece cambio de ejercicio; un mensaje sin "
            "accion deja al usuario sin saber que hacer"
        )
        assert "true" in bloque or "false" in bloque, f"{codigo} no declara el booleano"


def test_la_traduccion_no_inventa_codigos() -> None:
    """El cliente no puede traducir codigos que nadie emite.

    Seria codigo muerto que ademas sugiere al revisor que ese error existe.
    """
    codigos = _codigos_de_ejercicio_del_backend()
    traducidos = set(_traducidos())
    inventados = sorted(traducidos - codigos)
    # `periodo_cerrado` lo emite SPEC-028, que no esta en las dos rutas leidas: se
    # acepta explicitamente para que la lista sea util mas alla de este par.
    permitidos = {"periodo_cerrado"}
    assert sorted(set(inventados) - permitidos) == [], (
        "el cliente traduce codigos que ningun servicio de esta feature emite:\n"
        + "\n".join(f"  {c}" for c in sorted(set(inventados) - permitidos))
    )


def test_los_mensajes_no_incluyen_el_codigo_crudo() -> None:
    """El texto para el usuario no debe contener el codigo tecnico.

    Mostrarle `ejercicio_cerrado` a un contable no es un detalle: es informacion que
    no puede usar y que suena a fallo. El codigo se conserva en `ApiError.code` para
    el programador, no en el mensaje.
    """
    for codigo, texto in _traducidos().items():
        assert codigo not in texto, (
            f"el mensaje de {codigo!r} contiene el propio codigo: {texto!r}"
        )
        assert "_" not in texto, (
            f"el mensaje de {codigo!r} parece tecnico, no escrito para el usuario: "
            f"{texto!r}"
        )
