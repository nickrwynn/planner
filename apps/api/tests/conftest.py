from __future__ import annotations

import os

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.main import create_app


@pytest.fixture(scope="session")
def test_database_url(tmp_path_factory) -> str:
    # Use a file-based sqlite DB so multiple connections share the same DB.
    db_path = tmp_path_factory.mktemp("db") / "test.db"
    url = os.getenv("TEST_DATABASE_URL", f"sqlite+pysqlite:///{db_path}")
    return url


@pytest.fixture(scope="session")
def engine(test_database_url: str):
    engine_ = create_engine(test_database_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine_)
    yield engine_
    Base.metadata.drop_all(bind=engine_)


@pytest.fixture()
def db_session(engine):
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(test_database_url: str, engine, monkeypatch, tmp_path):
    # `engine` runs create_all so API and tests share the same SQLite schema.
    os.environ["DATABASE_URL"] = test_database_url
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
    os.environ["STORAGE_ROOT"] = str(tmp_path / "uploads")
    os.environ["AUTH_MODE"] = "dev"
    get_settings.cache_clear()
    fake_redis = fakeredis.FakeStrictRedis(decode_responses=False)
    monkeypatch.setattr("redis.Redis.from_url", lambda *args, **kwargs: fake_redis)
    app = create_app()

    with TestClient(app) as c:
        yield c

