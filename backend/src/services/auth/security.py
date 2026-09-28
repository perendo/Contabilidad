"""Password hashing (bcrypt) and JWT handling (SPEC-003 D10).

La clave de firma se toma de `SECRET_KEY` (alias historico `AUTH_JWT_SECRET`)
en `config.Settings`. **No existe ninguna constante conocida en el codigo**: si
el entorno no define un secreto valido, se genera uno aleatorio por proceso
(`SECRET_EPHEMERAL = True`) para que la firma nunca sea predecible ni
reproducible entre despliegues; `comprobar_configuracion()` avisa de ello y
`main.py` lo registra al arrancar.

Recomendacion de generacion: ``python -c "import secrets;
print(secrets.token_hex(32))"`` (64 caracteres hex = 256 bits).
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "ALGORITMOS_PERMITIDOS",
    "LONGITUD_MINIMA_SECRETO",
    "PLACEHOLDER_DEV",
    "SECRET_EPHEMERAL",
    "algoritmo",
    "comprobar_configuracion",
    "emit_token",
    "hash_password",
    "minutos_expiracion",
    "secreto",
    "verify_password",
    "verify_token",
]

#: Placeholder de SPEC-003 que se considera NO seguro (nunca se usa para firmar).
PLACEHOLDER_DEV = "dev-only-secret-change-me-to-32-bytes-min"
#: HMAC-SHA2 de PyJWT. Fijar la lista evita *algorithm confusion*.
ALGORITMOS_PERMITIDOS: frozenset[str] = frozenset({"HS256", "HS384", "HS512"})
#: Minimo 32 caracteres: por debajo, la firma ofrece menos de 256 bits utiles.
LONGITUD_MINIMA_SECRETO: int = 32


def _resolver_secreto(configurado: str) -> str:
    """Secreto efectivo: el del entorno o uno aleatorio de un solo proceso."""
    candidato = (configurado or "").strip()
    if not candidato or candidato == PLACEHOLDER_DEV:
        return secrets.token_urlsafe(48)
    if len(candidato) < LONGITUD_MINIMA_SECRETO:
        raise ValueError(
            "SECRET_KEY debe tener al menos "
            f"{LONGITUD_MINIMA_SECRETO} caracteres (tiene {len(candidato)})"
        )
    return candidato


secreto: str = _resolver_secreto(settings.secret_key)
algoritmo: str = (settings.algorithm or "HS256").strip().upper()
minutos_expiracion: int = max(1, int(settings.access_token_expire_minutes))

#: `True` cuando no hay secreto en el entorno y se ha generado uno aleatorio.
SECRET_EPHEMERAL: bool = secreto != (settings.secret_key or "").strip()


def comprobar_configuracion() -> list[str]:
    """Devuelve los avisos de configuracion (y los registra una vez)."""
    avisos: list[str] = []
    if algoritmo not in ALGORITMOS_PERMITIDOS:
        avisos.append(
            f"ALGORITHM={algoritmo} no es un algoritmo permitido "
            f"({', '.join(sorted(ALGORITMOS_PERMITIDOS))}); se usa HS256"
        )
    if SECRET_EPHEMERAL:
        avisos.append(
            "SECRET_KEY no esta definido en el entorno: se firmo con un secreto "
            "aleatorio de un solo proceso, por lo que los tokens no sobreviven a "
            "un reinicio. Define SECRET_KEY en .env"
        )
    for aviso in avisos:
        logger.warning("configuracion de autenticacion: %s", aviso)
    return avisos


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        return False


def emit_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "exp": now + timedelta(minutes=minutos_expiracion),
        "iat": now,
        "nbf": now,
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, secreto, algorithm=algoritmo)


def verify_token(token: str) -> int:
    payload = jwt.decode(
        token,
        secreto,
        algorithms=[algoritmo],
        options={"require": ["sub", "exp", "iat", "jti"]},
    )
    return int(payload["sub"])
