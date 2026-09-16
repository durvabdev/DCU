from app.database import resolve_database_url


def test_resolve_database_url_leaves_local_sqlite_alone(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    assert resolve_database_url("sqlite:///./bank.db") == "sqlite:///./bank.db"
