from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, case_sensitive=False)

    app_env: str = "dev"
    app_runtime_profile: str = "dev"
    database_url: str = "postgresql+psycopg://planner:planner@localhost:5432/planner"
    redis_url: str = "redis://localhost:6379/0"
    # Accept either JSON list (e.g. '["http://localhost:3000"]') or a comma-separated string
    cors_origins: list[str] | str = ["http://localhost:3000"]
    storage_root: str = "/data/uploads"
    storage_backend: str = "local"
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_endpoint_url: str | None = None
    auth_mode: str = "bearer"
    auth_jwt_secret: str = ""
    auth_jwt_algorithm: str = "HS256"
    auth_jwt_issuer: str | None = None
    auth_jwt_audience: str | None = None
    auth_jwt_leeway_seconds: int = 30
    telemetry_enabled: bool = False
    telemetry_service_name: str = "academic-os-api"
    rate_limit_enabled: bool = True
    rate_limit_window_seconds: int = 60
    rate_limit_max_requests: int = 120

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v):
        if v is None:
            return ["http://localhost:3000"]
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str):
            s = v.strip()
            # Allow single origin without JSON syntax
            if s and not s.startswith("["):
                return [p.strip() for p in s.split(",") if p.strip()]
        return v

    def is_production_profile(self) -> bool:
        env = str(self.app_env or "").strip().lower()
        profile = str(self.app_runtime_profile or "").strip().lower()
        return env in {"prod", "production"} or profile == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()

