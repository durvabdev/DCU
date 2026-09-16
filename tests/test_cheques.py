from fastapi.testclient import TestClient

from tests.conftest import extract_csrf


def test_order_cheque_book_debits_fee_on_checking(auth_client: TestClient):
    from app.database import SessionLocal
    from app.models import Account

    db = SessionLocal()
    try:
        account = db.get(Account, "CK-1001")
        assert account is not None
        before = account.balance_cents
    finally:
        db.close()

    member_page = auth_client.get("/members/001234")
    assert member_page.status_code == 200
    assert "Order cheque book" in member_page.text
    assert 'href="/members/001234/cheque-books/new"' in member_page.text

    page = auth_client.get("/members/001234/cheque-books/new")
    assert page.status_code == 200
    assert "Standard — 25 pages ($15.00)" in page.text
    assert "Business — 50 pages ($25.00)" in page.text
    assert "Premium — 100 pages ($40.00)" in page.text
    assert 'value="CK-1001"' in page.text
    csrf = extract_csrf(page.text)
    response = auth_client.post(
        "/members/001234/cheque-books/new",
        data={
            "csrf_token": csrf,
            "book_type": "business",
            "fee_account_id": "CK-1001",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/members/001234")

    member_after = auth_client.get(location)
    assert member_after.status_code == 200
    assert 'class="alert alert-success"' in member_after.text
    assert "Cheque book ordered. Debited $25.00 from CK-1001." in member_after.text
    assert "TX-CK-1001-" in member_after.text

    db = SessionLocal()
    try:
        account = db.get(Account, "CK-1001")
        assert account is not None
        assert account.balance_cents == before - 2500
    finally:
        db.close()


def test_order_cheque_book_can_debit_sibling_savings(auth_client: TestClient):
    from app.database import SessionLocal
    from app.models import Account

    db = SessionLocal()
    try:
        savings = db.get(Account, "SV-2010")
        assert savings is not None
        before = savings.balance_cents
    finally:
        db.close()

    page = auth_client.get("/members/002010/cheque-books/new")
    assert page.status_code == 200
    assert 'value="SV-2010"' in page.text
    csrf = extract_csrf(page.text)
    response = auth_client.post(
        "/members/002010/cheque-books/new",
        data={
            "csrf_token": csrf,
            "book_type": "standard",
            "fee_account_id": "SV-2010",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/members/002010")

    member_after = auth_client.get(location)
    assert member_after.status_code == 200
    assert 'class="alert alert-success"' in member_after.text
    assert "Cheque book ordered. Debited $15.00 from SV-2010." in member_after.text
    assert "TX-SV-2010-" in member_after.text

    db = SessionLocal()
    try:
        savings = db.get(Account, "SV-2010")
        checking = db.get(Account, "CK-2010")
        assert savings is not None and checking is not None
        assert savings.balance_cents == before - 1500
    finally:
        db.close()


def test_cheque_book_requires_csrf(auth_client: TestClient):
    response = auth_client.post(
        "/members/001234/cheque-books/new",
        data={
            "csrf_token": "invalid",
            "book_type": "standard",
            "fee_account_id": "CK-1001",
        },
    )
    assert response.status_code == 403
    assert "This form could not be verified." in response.text


def test_cheque_book_blocked_without_active_checking(auth_client: TestClient):
    response = auth_client.get("/members/004200/cheque-books/new")
    assert response.status_code == 403
    assert "Cheque books require an active checking account." in response.text

    account_page = auth_client.get("/accounts/CK-4200")
    assert account_page.status_code == 200
    assert "Order cheque book" not in account_page.text


def test_cheque_book_blocked_on_inactive_member(auth_client: TestClient):
    from app.database import SessionLocal
    from app.models import Member

    db = SessionLocal()
    try:
        member = db.get(Member, "001234")
        assert member is not None
        member.status = "inactive"
        db.commit()
    finally:
        db.close()

    response = auth_client.get("/members/001234/cheque-books/new")
    assert response.status_code == 403
    assert "Cheque books can only be ordered for active members." in response.text


def test_cheque_book_not_on_account_pages(auth_client: TestClient):
    savings_page = auth_client.get("/accounts/SV-5500")
    assert "Order cheque book" not in savings_page.text

    loan_page = auth_client.get("/accounts/LN-1001")
    assert "Order cheque book" not in loan_page.text

    checking_page = auth_client.get("/accounts/CK-1001")
    assert "Order cheque book" not in checking_page.text


def test_cheque_book_rejects_overdraft(auth_client: TestClient):
    from app.database import SessionLocal
    from app.models import Account

    db = SessionLocal()
    try:
        account = db.get(Account, "CK-5500")
        assert account is not None
        account.balance_cents = 1000
        db.commit()
    finally:
        db.close()

    page = auth_client.get("/members/005500/cheque-books/new")
    csrf = extract_csrf(page.text)
    response = auth_client.post(
        "/members/005500/cheque-books/new",
        data={
            "csrf_token": csrf,
            "book_type": "standard",
            "fee_account_id": "CK-5500",
        },
    )
    assert response.status_code == 200
    assert "Cheque book fee would make the fee account balance negative." in response.text


def test_cheque_book_rejects_foreign_fee_account(auth_client: TestClient):
    page = auth_client.get("/members/001234/cheque-books/new")
    csrf = extract_csrf(page.text)
    response = auth_client.post(
        "/members/001234/cheque-books/new",
        data={
            "csrf_token": csrf,
            "book_type": "standard",
            "fee_account_id": "CK-2001",
        },
    )
    assert response.status_code == 200
    assert "Select a valid fee debit account." in response.text
