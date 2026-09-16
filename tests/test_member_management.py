from fastapi.testclient import TestClient

from tests.conftest import extract_csrf


def test_member_edit_updates_profile(auth_client: TestClient):
    edit_page = auth_client.get("/members/001234/edit")
    csrf = extract_csrf(edit_page.text)
    response = auth_client.post(
        "/members/001234/edit",
        data={
            "csrf_token": csrf,
            "first_name": "Elena",
            "last_name": "Vargas",
            "email": "elena.vargas@example.com",
            "phone": "(602) 555-0142",
            "street": "500 Updated Ave",
            "city": "Phoenix",
            "state": "AZ",
            "postal_code": "85007",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Member profile updated." in response.text
    assert "500 Updated Ave" in response.text


def test_member_edit_requires_csrf(auth_client: TestClient):
    response = auth_client.post(
        "/members/001234/edit",
        data={
            "csrf_token": "invalid",
            "first_name": "Elena",
            "last_name": "Vargas",
            "email": "elena.vargas@example.com",
            "phone": "(602) 555-0142",
            "street": "Any St",
            "city": "Phoenix",
            "state": "AZ",
            "postal_code": "85007",
        },
    )
    assert response.status_code == 403
    assert "This form could not be verified." in response.text


def test_member_edit_rejects_empty_required_fields(auth_client: TestClient):
    edit_page = auth_client.get("/members/001234/edit")
    csrf = extract_csrf(edit_page.text)
    response = auth_client.post(
        "/members/001234/edit",
        data={
            "csrf_token": csrf,
            "first_name": "",
            "last_name": "Vargas",
            "email": "elena.vargas@example.com",
            "phone": "(602) 555-0142",
            "street": "Any St",
            "city": "Phoenix",
            "state": "AZ",
            "postal_code": "85007",
        },
    )
    assert response.status_code == 200
    assert "First Name is required." in response.text


def test_open_account_creates_savings_account(auth_client: TestClient):
    page = auth_client.get("/members/001234/accounts/new")
    csrf = extract_csrf(page.text)
    response = auth_client.post(
        "/members/001234/accounts/new",
        data={
            "csrf_token": csrf,
            "account_type": "savings",
            "opening_amount": "123.45",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/accounts/SV-5501"

    account = auth_client.get("/accounts/SV-5501")
    assert account.status_code == 200
    assert "$123.45" in account.text


def test_open_account_rejects_inactive_member(auth_client: TestClient):
    from app.database import SessionLocal
    from app.models import Member

    db = SessionLocal()
    try:
        member = db.get(Member, "004200")
        assert member is not None
        member.status = "inactive"
        db.commit()
    finally:
        db.close()

    response = auth_client.get("/members/004200/accounts/new")
    assert response.status_code == 403
    assert "New accounts can only be opened for active members." in response.text


def test_member_edit_redirects_when_anonymous(client: TestClient):
    response = client.post("/members/001234/edit", data={"first_name": "Elena"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")
