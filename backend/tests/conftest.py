import os
import tempfile

# Must happen before any `app.*` import: app/config.py resolves data-dir paths
# (secret key, session key, sqlite path) from these env vars at import time.
_TEST_DATA_DIR = tempfile.mkdtemp(prefix="haven_backup_test_")
os.environ["HAVEN_DATA_DIR"] = _TEST_DATA_DIR
os.environ["HAVEN_DISABLE_SCHEDULER"] = "1"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app import db as db_module
from app import rate_limit
from app.main import app
from app.routers import version as version_router


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    # The limiter's attempt counts are a module-level global (see app/rate_limit.py) --
    # without this, an early test's login/setup calls would count against a later
    # test's rate-limit budget, since TestClient requests all share one fake client IP.
    rate_limit.reset()
    yield


@pytest.fixture(autouse=True)
def _reset_version_cache():
    version_router.reset_cache()
    yield


@pytest.fixture
def test_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(test_engine):
    with Session(test_engine) as session:
        yield session


@pytest.fixture
def client(test_engine):
    def get_session_override():
        with Session(test_engine) as session:
            yield session

    app.dependency_overrides[db_module.get_session] = get_session_override
    # https:// base_url: config.COOKIE_SECURE defaults to True (see app/config.py),
    # and httpx's cookie jar -- like a real browser -- refuses to persist a Secure
    # cookie set over plain http, which would otherwise break every test that logs
    # in and then makes a follow-up authenticated request.
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()
