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


def test_open_account_creates_savings_account_at_zero(auth_client: TestClient):
    page = auth_client.get("/members/001234/accounts/new")
    assert "Opening amount" not in page.text
    csrf = extract_csrf(page.text)
    response = auth_client.post(
        "/members/001234/accounts/new",
        data={
            "csrf_token": csrf,
            "account_type": "savings",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/members/001234/accounts/new")
    assert "opened=SV-5501" in location

    form_after = auth_client.get(location)
    assert form_after.status_code == 200
    assert 'class="alert alert-success"' in form_after.text
    assert "Account opened. SV-5501" in form_after.text
    assert "disabled" in form_after.text
    assert "<button type=\"submit\" disabled>Open account</button>" in form_after.text

    account = auth_client.get("/accounts/SV-5501")
    assert account.status_code == 200
    assert "$0.00" in account.text


def test_open_account_form_does_not_offer_loan(auth_client: TestClient):
    page = auth_client.get("/members/001234/accounts/new")
    assert page.status_code == 200
    assert 'value="loan"' not in page.text
    assert 'value="checking"' in page.text
    assert 'value="savings"' in page.text


def test_open_account_rejects_loan_type_on_member_path(auth_client: TestClient):
    page = auth_client.get("/members/001234/accounts/new")
    csrf = extract_csrf(page.text)
    response = auth_client.post(
        "/members/001234/accounts/new",
        data={
            "csrf_token": csrf,
            "account_type": "loan",
        },
    )
    assert response.status_code == 200
    assert "Select a valid account type." in response.text


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


def test_home_links_to_open_loan(auth_client: TestClient):
    home = auth_client.get("/")
    assert home.status_code == 200
    assert 'href="/loans/new"' in home.text
    assert "Open loan" in home.text


def test_open_loan_for_marcus_chen(auth_client: TestClient):
    search = auth_client.get("/loans/new", params={"q": "002001"})
    assert search.status_code == 200
    assert "Marcus Chen" in search.text
    assert 'href="/loans/new/002001"' in search.text
    assert "Continue" in search.text

    form = auth_client.get("/loans/new/002001")
    assert form.status_code == 200
    csrf = extract_csrf(form.text)
    response = auth_client.post(
        "/loans/new/002001",
        data={
            "csrf_token": csrf,
            "outstanding_balance": "1500.00",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/loans/new/002001")
    assert "opened=LN-6601" in location

    form_after = auth_client.get(location)
    assert form_after.status_code == 200
    assert 'class="alert alert-success"' in form_after.text
    assert "Account opened. LN-6601" in form_after.text
    assert "disabled" in form_after.text
    assert "<button type=\"submit\" disabled>Open loan</button>" in form_after.text

    account = auth_client.get("/accounts/LN-6601")
    assert account.status_code == 200
    assert "Outstanding balance" in account.text
    assert "$1,500.00" in account.text


def test_open_loan_rejects_inactive_member(auth_client: TestClient):
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

    response = auth_client.get("/loans/new/004200")
    assert response.status_code == 403
    assert "New loans can only be opened for active members." in response.text


def test_open_loan_requires_csrf(auth_client: TestClient):
    response = auth_client.post(
        "/loans/new/002001",
        data={
            "csrf_token": "invalid",
            "outstanding_balance": "100.00",
        },
    )
    assert response.status_code == 403
    assert "This form could not be verified." in response.text
