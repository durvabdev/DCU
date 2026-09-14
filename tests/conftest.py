from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database import SessionLocal, get_engine, init_engine
from app.main import create_app
from app.seed import DEMO_EMPLOYEES, seed_database

ADMIN = DEMO_EMPLOYEES[0]


def extract_csrf(html: str) -> str:
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert match, "csrf_token was not found in the page"
    return match.group(1)


@pytest.fixture(scope="session")
def seeded_db_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    db_path = tmp_path_factory.mktemp("seed") / "bank.db"
    init_engine(f"sqlite:///{db_path}")
    db = SessionLocal()
    try:
        seed_database(db)
        db.commit()
    finally:
        db.close()
        get_engine().dispose()
    return db_path


@pytest.fixture
def db_path(seeded_db_path: Path, tmp_path: Path) -> Path:
    copied = tmp_path / "bank.db"
    shutil.copy(seeded_db_path, copied)
    return copied


@pytest.fixture
def app(db_path: Path):
    return create_app(
        Settings(
            database_url=f"sqlite:///{db_path}",
            session_secret="test-session-secret",
            dev_scenarios_enabled=True,
            session_ttl_hours=8,
        )
    )


@pytest.fixture
def client(app) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_client(client: TestClient) -> TestClient:
    login(client)
    return client


def login(client: TestClient, username: str | None = None, password: str | None = None) -> None:
    page = client.get("/login")
    assert page.status_code == 200
    response = client.post(
        "/login",
        data={
            "csrf_token": extract_csrf(page.text),
            "username": username or ADMIN["username"],
            "password": password or ADMIN["password"],
            "next": "/",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"
