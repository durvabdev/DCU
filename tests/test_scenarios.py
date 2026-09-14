from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.conftest import extract_csrf


def test_scenarios_hidden_when_flag_off(db_path):
    app = create_app(
        Settings(
            database_url=f"sqlite:///{db_path}",
            session_secret="test-session-secret",
            dev_scenarios_enabled=False,
            session_ttl_hours=8,
        )
    )
    with TestClient(app) as client:
        response = client.get("/dev/scenarios")
        assert response.status_code == 404
        assert "Development scenarios" not in response.text
        posted = client.post("/dev/scenarios", data={"action": "reset"})
        assert posted.status_code == 404


def test_scenarios_available_when_flag_on(auth_client: TestClient):
    response = auth_client.get("/dev/scenarios")
    assert response.status_code == 200
    assert "Development scenarios" in response.text
    assert "Reset demonstration data" in response.text


def test_ui_variation_renames_apply_filters(auth_client: TestClient):
    page = auth_client.get("/dev/scenarios")
    auth_client.post(
        "/dev/scenarios",
        data={"csrf_token": extract_csrf(page.text), "action": "ui-variation"},
        follow_redirects=True,
    )
    account = auth_client.get("/accounts/LN-1001")
    assert "Search Transactions" in account.text
    assert 'data-testid="apply-filters"' in account.text
