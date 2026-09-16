from fastapi.testclient import TestClient

from app.models import PortalSession
from tests.conftest import extract_csrf, login


def test_invalid_login_shows_error(client: TestClient):
    page = client.get("/login")
    response = client.post(
        "/login",
        data={
            "csrf_token": extract_csrf(page.text),
            "username": "j.patel",
            "password": "not-the-password",
            "next": "/",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "username or password is incorrect" in response.text
    home = client.get("/", follow_redirects=False)
    assert home.status_code == 303
    assert "/login" in home.headers["location"]


def test_successful_login_reaches_home(auth_client: TestClient):
    response = auth_client.get("/")
    assert response.status_code == 200
    assert "Home" in response.text
    assert "Jordan Patel" in response.text
    assert "teller (T-1001)" in response.text
    assert 'href="/members"' in response.text
    assert "Log out" in response.text


def test_teller_details_page(auth_client: TestClient):
    response = auth_client.get("/teller")
    assert response.status_code == 200
    assert "<h1>Jordan Patel</h1>" in response.text
    assert 'href="/teller"' in response.text
    assert "teller (T-1001)" in response.text


def test_login_survives_missing_session_row(auth_client: TestClient):
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        db.query(PortalSession).delete()
        db.commit()
    finally:
        db.close()

    response = auth_client.get("/", follow_redirects=False)
    assert response.status_code == 200
    assert "Jordan Patel" in response.text
    assert "Home" in response.text


def test_protected_route_redirects_when_anonymous(client: TestClient):
    response = client.get("/members/001234", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")
    assert "001234" in response.headers["location"]


def test_expired_session_does_not_process_post(auth_client: TestClient):
    scenarios = auth_client.get("/dev/scenarios")
    csrf = extract_csrf(scenarios.text)
    queued = auth_client.post(
        "/dev/scenarios",
        data={"csrf_token": csrf, "action": "expire"},
        follow_redirects=True,
    )
    assert queued.status_code == 200
    assert "Session expiry queued" in queued.text

    form = auth_client.get("/transactions/TX-LN-1001-F01/notes/new", follow_redirects=True)
    # Expiry fires on this protected GET, so the note form is not shown.
    assert form.status_code == 200
    assert "Sign in" in form.text
    assert "Add investigation note" not in form.text
