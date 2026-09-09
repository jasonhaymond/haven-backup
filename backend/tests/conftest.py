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
from app.main import app


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
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
