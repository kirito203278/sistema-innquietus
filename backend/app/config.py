from functools import lru_cache

import base64
import binascii

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str
    jwt_secret: str
    aes_key_b64: str
    jobs_secret: str

    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 12
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    tz: str = "America/Mexico_City"
    agencia_nombre: str = "INNquietus"
    scheduler_enabled: bool = True
    enable_docs: bool = False

    ciclo_dias: int = 30
    prorroga_max_dias: int = 5
    dias_para_decidir: int = 2
    aviso_dias_antes_renovacion: int = 4
    aviso_prorroga_dias: int = 3
    purga_meses: int = 12
    reingreso_meses: int = 2

    @field_validator("database_url")
    @classmethod
    def _normalizar_url_bd(cls, v: str) -> str:
        for prefijo in ("postgres://", "postgresql://"):
            if v.startswith(prefijo):
                return "postgresql+psycopg2://" + v[len(prefijo):]
        return v

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_fuerte(cls, v: str) -> str:
        if len(v) < 32 or v.startswith("__"):
            raise ValueError("JWT_SECRET debe tener al menos 32 caracteres (genera uno con scripts/generar_env.py)")
        return v

    @field_validator("jobs_secret")
    @classmethod
    def _jobs_fuerte(cls, v: str) -> str:
        if len(v) < 16 or v.startswith("__"):
            raise ValueError("JOBS_SECRET debe tener al menos 16 caracteres (genera uno con scripts/generar_env.py)")
        return v

    @field_validator("aes_key_b64")
    @classmethod
    def _aes_valida(cls, v: str) -> str:
        try:
            ok = len(base64.b64decode(v, validate=True)) == 32
        except (binascii.Error, ValueError):
            ok = False
        if not ok:
            raise ValueError("AES_KEY_B64 debe ser una clave de 32 bytes en base64 (genera una con scripts/generar_env.py)")
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
