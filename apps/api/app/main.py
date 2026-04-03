from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis import Redis

from app.core.config import Settings, get_settings
from app.db.session import check_db, create_db_engine, create_session_factory
from app.api.routes.courses import router as courses_router
from app.api.routes.notebooks import router as notebooks_router
from app.api.routes.resources import router as resources_router
from app.api.routes.tasks import router as tasks_router
from app.api.routes.search import router as search_router
from app.api.routes.ai import router as ai_router
from app.api.routes.notes import router as notes_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.planner import router as planner_router
from app.api.middleware.rate_limit import RedisRateLimiter, make_rate_limit_middleware
from app.core.telemetry import emit_diagnostic, setup_telemetry


def _assert_production_safe_settings(settings: Settings) -> None:
    if not settings.is_production_profile():
        return

    errors: list[str] = []
    if str(settings.auth_mode or "").strip().lower() != "bearer":
        errors.append("AUTH_MODE must be 'bearer' in production profile")

    secret = str(settings.auth_jwt_secret or "").strip()
    weak_markers = ("change-me", "dev-secret", "default", "test-secret")
    if len(secret) < 32 or any(marker in secret.lower() for marker in weak_markers):
        errors.append("AUTH_JWT_SECRET must be a strong secret (>=32 chars, non-default) in production profile")

    origins = settings.cors_origins if isinstance(settings.cors_origins, list) else [settings.cors_origins]
    cleaned = [str(o).strip() for o in origins if str(o).strip()]
    if not cleaned or "*" in cleaned:
        errors.append("CORS_ORIGINS must be an explicit non-empty allowlist in production profile")

    if not settings.rate_limit_enabled:
        errors.append("RATE_LIMIT_ENABLED must be true in production profile")

    if errors:
        raise RuntimeError("Invalid production configuration: " + "; ".join(errors))


def create_app() -> FastAPI:
    settings = get_settings()
    _assert_production_safe_settings(settings)

    app = FastAPI(title="Academic OS API", version="0.1.0")
    emit_diagnostic(
        "api_startup",
        service="api",
        correlation_id="service:api",
        telemetry_enabled=settings.telemetry_enabled,
        profile=settings.app_runtime_profile,
        auth_mode=settings.auth_mode,
        rate_limit_enabled=settings.rate_limit_enabled,
    )

    # DB engine/session lifecycle (singleton per process)
    engine = create_db_engine(settings.database_url)
    app.state.db_engine = engine
    app.state.db_sessionmaker = create_session_factory(engine)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    if settings.rate_limit_enabled:
        limiter = RedisRateLimiter(
            redis=Redis.from_url(settings.redis_url),
            window_seconds=settings.rate_limit_window_seconds,
            max_requests=settings.rate_limit_max_requests,
        )
        app.middleware("http")(make_rate_limit_middleware(limiter))

    @app.get("/health")
    def health():
        postgres_ok = True
        postgres_error: str | None = None
        redis_ok = True
        redis_error: str | None = None

        # Postgres check
        try:
            check_db(app.state.db_engine)
        except Exception as e:  # noqa: BLE001 (bootstrap-friendly visibility)
            postgres_ok = False
            postgres_error = str(e)

        # Redis check
        try:
            r = Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)
            r.ping()
        except Exception as e:  # noqa: BLE001
            redis_ok = False
            redis_error = str(e)

        is_degraded = not postgres_ok or not redis_ok
        status = {
            "status": "degraded" if is_degraded else "ok",
            "postgres": {"ok": postgres_ok, "error": postgres_error},
            "redis": {"ok": redis_ok, "error": redis_error},
        }
        if is_degraded:
            emit_diagnostic(
                "health_degraded",
                level="warning",
                service="api",
                correlation_id="service:api",
                postgres_ok=postgres_ok,
                postgres_error=postgres_error,
                redis_ok=redis_ok,
                redis_error=redis_error,
            )
            return JSONResponse(status_code=503, content=status)
        return status

    app.include_router(courses_router)
    app.include_router(tasks_router)
    app.include_router(resources_router)
    app.include_router(notebooks_router)
    app.include_router(search_router)
    app.include_router(ai_router)
    app.include_router(notes_router)
    app.include_router(jobs_router)
    app.include_router(planner_router)

    if settings.telemetry_enabled:
        setup_telemetry(app, service_name=settings.telemetry_service_name)
        emit_diagnostic(
            "telemetry_enabled",
            service=settings.telemetry_service_name,
            correlation_id="service:api",
        )

    return app

