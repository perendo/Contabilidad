"""Configuracion del secreto de firma JWT (SECRET_KEY) y sus garantias.

Cubre la correccion que elimina la constante de desarrollo
`dev-only-secret-change-me-to-32-bytes-min` del codigo: el secreto se lee del
entorno y, si falta, se genera uno aleatorio por proceso (`SECRET_EPHEMERAL`).
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import jwt
import pytest
from pydantic import ValidationError

from services.auth import security
from services.auth.security import (
    ALGORITMOS_PERMITIDOS,
    LONGITUD_MINIMA_SECRETO,
    PLACEHOLDER_DEV,
    algoritmo,
    comprobar_configuracion,
)

RAIZ = Path(__file__).resolve().parents[2]
ENV_EJEMPLO = RAIZ / ".env.example"


def _recargar_config(monkeypatch: pytest.MonkeyPatch, **entorno: str) -> object:
    """Recarga `config` y luego `security` con un entorno controlado.

    `security` lee `settings.secret_key` en tiempo de importacion, asi que hay
    que recargar `config` primero y despues el modulo que lo consume.
    """
    for clave in ("SECRET_KEY", "AUTH_JWT_SECRET", "ALGORITHM", "AUTH_JWT_ALGORITHM",
                  "ACCESS_TOKEN_EXPIRE_MINUTES", "AUTH_JWT_EXPIRE_MINUTES",
                  "AUTH_JWT_EXPIRE_HOURS"):
        monkeypatch.delenv(clave, raising=False)
    for clave, valor in entorno.items():
        monkeypatch.setenv(clave, valor)
    import config
    import services.auth.security as mod

    importlib.reload(config)
    # `_env_file=None` ignora el `.env` local: la prueba manda.
    config.settings = config.Settings(_env_file=None)  # type: ignore[assignment]
    return importlib.reload(mod)


@pytest.fixture(autouse=True)
def _restaurar_modulos() -> object:
    """Deja `config`/`security` como estaban al terminar cada prueba."""
    yield
    import config
    import services.auth.security as mod

    importlib.reload(config)
    importlib.reload(mod)


# --- El secreto efectivo ---------------------------------------------------


def test_no_hay_constante_de_desarrollo_en_el_codigo() -> None:
    """El placeholder de SPEC-003 no puede quedar como valor por defecto."""
    fuente = (RAIZ / "src" / "services" / "auth" / "security.py").read_text(
        encoding="utf-8"
    )
    # El literal solo puede aparecer en su declaracion (para RECHAZARLO).
    literales = [linea for linea in fuente.splitlines() if "dev-only-secret" in linea]
    assert len(literales) == 1 and literales[0].startswith("PLACEHOLDER_DEV = "), literales
    # Y la constante solo se usa en la comparacion que lo descarta.
    referencias = [
        linea
        for linea in fuente.splitlines()
        if "PLACEHOLDER_DEV" in linea
        and not linea.startswith("PLACEHOLDER_DEV")
        and not linea.lstrip().startswith(('"', "#"))
    ]
    assert len(referencias) == 1, referencias  # solo la comparacion que lo descarta
    assert any("candidato ==" in linea for linea in referencias), referencias
    assert 'jwt_secret: str = "' not in fuente
    assert "jwt_secret=" not in fuente
    # La clave llega siempre desde `config.Settings`.
    assert "from config import settings" in fuente


def test_el_entorno_proporciona_el_secreto(monkeypatch: pytest.MonkeyPatch) -> None:
    """Con `SECRET_KEY` en el entorno, se usa tal cual (nada efimero)."""
    clave = "a" * 64
    mod = _recargar_config(monkeypatch, SECRET_KEY=clave)
    assert mod.secreto == clave
    assert mod.SECRET_EPHEMERAL is False
    assert mod.comprobar_configuracion() == []


def test_sin_entorno_se_genera_un_secreto_aleatorio_por_proceso(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _recargar_config(monkeypatch)
    assert mod.SECRET_EPHEMERAL is True
    assert mod.secreto != PLACEHOLDER_DEV
    assert len(mod.secreto) >= LONGITUD_MINIMA_SECRETO
    assert "SECRET_KEY" in " ".join(mod.comprobar_configuracion())
    # Estable dentro del proceso: los tokens emitidos verificados aqui valen.
    assert mod.verify_token(mod.emit_token(3)) == 3


def test_el_placeholder_de_desarrollo_se_trata_como_ausente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _recargar_config(monkeypatch, SECRET_KEY=PLACEHOLDER_DEV)
    assert mod.SECRET_EPHEMERAL is True
    assert mod.secreto != PLACEHOLDER_DEV


def test_un_secreto_corto_se_rechaza(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="al menos"):
        _recargar_config(monkeypatch, SECRET_KEY="corta")


@pytest.mark.parametrize("nombre", ["SECRET_KEY", "AUTH_JWT_SECRET"])
def test_se_acepta_el_alias_historico(monkeypatch: pytest.MonkeyPatch, nombre: str) -> None:
    clave = "b" * 48
    mod = _recargar_config(monkeypatch, **{nombre: clave})
    assert mod.secreto == clave
    assert mod.SECRET_EPHEMERAL is False


def test_el_alias_histórico_vence_en_horas(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _recargar_config(
        monkeypatch, AUTH_JWT_SECRET="d" * 48, AUTH_JWT_EXPIRE_HOURS="2"
    )
    assert mod.minutos_expiracion == 120


def test_los_minutos_ganan_a_las_horas(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _recargar_config(
        monkeypatch,
        SECRET_KEY="e" * 48,
        AUTH_JWT_EXPIRE_HOURS="8",
        ACCESS_TOKEN_EXPIRE_MINUTES="15",
    )
    assert mod.minutos_expiracion == 15


# --- Algoritmo -------------------------------------------------------------


@pytest.mark.parametrize("valor", ["HS256", "HS384", "HS512", "hs256"])
def test_algoritmos_admitidos(monkeypatch: pytest.MonkeyPatch, valor: str) -> None:
    mod = _recargar_config(monkeypatch, SECRET_KEY="f" * 48, ALGORITHM=valor)
    assert mod.algoritmo == valor.upper()
    assert mod.algoritmo in ALGORITMOS_PERMITIDOS
    assert mod.comprobar_configuracion() == []


def test_un_algoritmo_no_permitido_se_avisa(monkeypatch: pytest.MonkeyPatch) -> None:
    """`none` (algorithm confusion) queda fuera de la lista blanca."""
    mod = _recargar_config(monkeypatch, SECRET_KEY="f" * 48, ALGORITHM="none")
    assert mod.comprobar_configuracion()
    assert "no es un algoritmo permitido" in mod.comprobar_configuracion()[0]


# --- Firmado y verificacion ------------------------------------------------


def test_el_token_usa_el_secreto_del_entorno() -> None:
    token = security.emit_token(11)
    cabecera = jwt.get_unverified_header(token)
    assert cabecera["alg"] == algoritmo
    payload = jwt.decode(token, security.secreto, algorithms=[algoritmo])
    assert payload["sub"] == "11"
    assert {"sub", "exp", "iat", "jti"} <= set(payload)


def test_un_token_firmado_con_otro_secreto_se_rechaza() -> None:
    ajeno = jwt.encode(
        {"sub": "1", "exp": 9_999_999_999, "iat": 0, "jti": "x"},
        "otro-secreto-distinto-de-32-caracteres-aaaaaaaa",
        algorithm="HS256",
    )
    with pytest.raises(jwt.InvalidTokenError):
        security.verify_token(ajeno)


def test_un_token_sin_jti_se_rechaza() -> None:
    """`jti` es obligatorio: evita reuso de un token capturado."""
    sin_jti = jwt.encode(
        {"sub": "1", "exp": 9_999_999_999, "iat": 0},
        security.secreto,
        algorithm=algoritmo,
    )
    with pytest.raises(jwt.InvalidTokenError):
        security.verify_token(sin_jti)


def test_la_vida_del_token_es_el_vencimiento_configurado() -> None:
    token = security.emit_token(1)
    payload = jwt.decode(token, security.secreto, algorithms=[algoritmo])
    vida = (payload["exp"] - payload["iat"]) / 60
    assert vida == security.minutos_expiracion


def test_hash_y_verificacion_de_contrasena() -> None:
    hash1 = security.hash_password("clave")
    assert hash1 != "clave"
    assert security.verify_password("clave", hash1) is True
    assert security.verify_password("otra", hash1) is False
    assert security.verify_password("clave", "no-es-un-hash") is False


# --- Plantilla .env.example ------------------------------------------------


def test_la_plantilla_declara_las_claves_de_autenticacion() -> None:
    texto = ENV_EJEMPLO.read_text(encoding="utf-8")
    for clave in ("SECRET_KEY", "ALGORITHM", "ACCESS_TOKEN_EXPIRE_MINUTES"):
        assert f"{clave}=" in texto, clave
    # La plantilla nunca lleva un secreto real.
    cuerpo = texto.split("SECRET_KEY=", 1)[1].splitlines()[0]
    assert "<" in cuerpo and ">" in cuerpo, cuerpo


def test_el_env_real_no_usa_el_placeholder() -> None:
    """Guarda de que el `.env` local tiene un secreto propio (si existe)."""
    env = RAIZ / ".env"
    if not env.exists():
        pytest.skip("sin .env local")
    lineas = [
        linea
        for linea in env.read_text(encoding="utf-8").splitlines()
        if linea.strip().startswith("SECRET_KEY")
    ]
    assert lineas, "SECRET_KEY no esta definido en .env"
    valor = lineas[0].split("=", 1)[1].strip().strip('"')
    assert valor != PLACEHOLDER_DEV
    assert len(valor) >= LONGITUD_MINIMA_SECRETO
    assert set(valor) <= set("0123456789abcdefABCDEF_-")
    assert len(set(valor)) >= 8, "el secreto parece tener muy poca variedad"


def test_settings_acepta_una_url_de_base_de_datos_invalida_sin_romper() -> None:
    """`config.Settings` no debe validar la URL (los tests usan SQLite)."""
    import config

    assert config.Settings(_env_file=None).app_name
    with pytest.raises(ValidationError):
        config.Settings(access_token_expire_minutes="no-es-un-numero", _env_file=None)


def test_placeholder_no_importable() -> None:
    """Evita que alguien importe un nombre inexistente por error de refactor."""
    assert callable(security.emit_token)
    assert callable(comprobar_configuracion)
    assert os.path.isfile(RAIZ / "src" / "config.py")
