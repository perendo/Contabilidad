"""Configuración de la aplicación, derivada de variables de entorno.

Variables reconocidas: ``APP_NAME``, ``APP_VERSION``, ``DATABASE_URL``,
``CORS_ORIGINS`` (lista separada por comas), ``SECRET_KEY`` (clave de firma de
los JWT), ``ALGORITHM``, ``ACCESS_TOKEN_EXPIRE_MINUTES`` y los limites de
documentos adjuntos de SPEC-030 (``DOCUMENTO_MAX_BYTES``,
``DOCUMENTO_MAX_PAGINAS``, ``DOCUMENTO_MAX_POR_ASIENTO`` y
``DOCUMENTO_PLAZO_CONSERVACION_ANOS``).

Por compatibilidad con el nombre historico del modulo, ``SECRET_KEY`` admite
tambien ``AUTH_JWT_SECRET``, ``ALGORITHM`` admite ``AUTH_JWT_ALGORITHM`` y el
vencimiento acepta ``ACCESS_TOKEN_EXPIRE_MINUTES``, ``AUTH_JWT_EXPIRE_MINUTES``
o ``AUTH_JWT_EXPIRE_HOURS`` (convertido a minutos).

Los valores por defecto son de desarrollo: `secret_key` vacio hace que
`services.auth.security` genere un secreto aleatorio **por proceso** en vez de
usar una constante conocida (ver `SECRET_EPHEMERAL`).
"""

from __future__ import annotations

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "ContabilidadV1"
    app_version: str = "0.1.0"
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/contabilidad"
    )
    cors_origins: str = "http://localhost:3000"
    secret_key: str = Field(
        default="",
        validation_alias=AliasChoices("SECRET_KEY", "AUTH_JWT_SECRET"),
    )
    algorithm: str = Field(
        default="HS256",
        validation_alias=AliasChoices("ALGORITHM", "AUTH_JWT_ALGORITHM"),
    )
    access_token_expire_minutes: int = Field(
        default=30,
        validation_alias=AliasChoices(
            "ACCESS_TOKEN_EXPIRE_MINUTES", "AUTH_JWT_EXPIRE_MINUTES"
        ),
    )
    #: Antiguedad de SPEC-003 (12 h). Solo se aplica si el vencimiento en
    #: minutos no viene explicito en el entorno.
    auth_jwt_expire_hours: int = Field(
        default=12, validation_alias="AUTH_JWT_EXPIRE_HOURS"
    )
    #: Limites operativos de SPEC-030 (research D10). FR-003 fija 10 MB por
    #: documento; los otros tres son guardas de rendimiento (SC-008) y de
    #: conservación. Son parametros de entorno, no constantes de modulo: el
    #: unico limite de subida previo era la constante `MAX_BYTES` de
    #: `api/importexport.py`, sin forma de variarlo por instalacion.
    documento_max_bytes: int = 10 * 1024 * 1024
    documento_max_paginas: int = 200
    documento_max_por_asiento: int = 50
    #: Plazo legal de conservacion de facturas y justificantes (art. 30 LGT).
    documento_plazo_conservacion_anos: int = 6

    model_config = {"env_file": ".env", "extra": "ignore"}

    @model_validator(mode="after")
    def _minutos_ganan_a_horas(self) -> Settings:
        if (
            "access_token_expire_minutes" not in self.model_fields_set
            and "auth_jwt_expire_hours" in self.model_fields_set
        ):
            object.__setattr__(
                self,
                "access_token_expire_minutes",
                self.auth_jwt_expire_hours * 60,
            )
        return self

    @property
    def cors_origins_list(self) -> list[str]:
        return [
            origen.strip() for origen in self.cors_origins.split(",") if origen.strip()
        ]


settings = Settings()
