from fastapi.testclient import TestClient

from tests.conftest import extract_csrf


def test_cheque_deposit_on_checking_updates_balance(auth_client: TestClient):
    from app.database import SessionLocal
    from app.models import Account

    db = SessionLocal()
    try:
        account = db.get(Account, "CK-1001")
        assert account is not None
        before = account.balance_cents
    finally:
        db.close()

    page = auth_client.get("/accounts/CK-1001/cheques/new")
    assert page.status_code == 200
    assert 'value="deposit"' in page.text
    assert 'value="withdrawal"' in page.text
    csrf = extract_csrf(page.text)
    response = auth_client.post(
        "/accounts/CK-1001/cheques/new",
        data={
            "csrf_token": csrf,
            "cheque_number": "1042",
            "amount": "25.50",
            "direction": "deposit",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/transactions/")

    txn_page = auth_client.get(location)
    assert txn_page.status_code == 200
    assert "Cheque deposit #1042" in txn_page.text
    assert "$25.50" in txn_page.text
    assert "credit" in txn_page.text

    db = SessionLocal()
    try:
        account = db.get(Account, "CK-1001")
        assert account is not None
        assert account.balance_cents == before + 2550
    finally:
        db.close()


def test_cheque_payment_on_loan_reduces_outstanding(auth_client: TestClient):
    from app.database import SessionLocal
    from app.models import Account

    db = SessionLocal()
    try:
        account = db.get(Account, "LN-1001")
        assert account is not None
        before = account.balance_cents
    finally:
        db.close()

    page = auth_client.get("/accounts/LN-1001/cheques/new")
    assert page.status_code == 200
    assert 'value="payment"' in page.text
    assert 'value="deposit"' not in page.text
    csrf = extract_csrf(page.text)
    response = auth_client.post(
        "/accounts/LN-1001/cheques/new",
        data={
            "csrf_token": csrf,
            "cheque_number": "88",
            "amount": "100.00",
            "direction": "payment",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/transactions/")

    txn_page = auth_client.get(location)
    assert "Cheque payment #88" in txn_page.text

    db = SessionLocal()
    try:
        account = db.get(Account, "LN-1001")
        assert account is not None
        assert account.balance_cents == before - 10000
    finally:
        db.close()


def test_cheque_requires_csrf(auth_client: TestClient):
    response = auth_client.post(
        "/accounts/CK-1001/cheques/new",
        data={
            "csrf_token": "invalid",
            "cheque_number": "1",
            "amount": "10.00",
            "direction": "deposit",
        },
    )
    assert response.status_code == 403
    assert "This form could not be verified." in response.text


def test_cheque_blocked_on_inactive_account(auth_client: TestClient):
    response = auth_client.get("/accounts/CK-4200/cheques/new")
    assert response.status_code == 403
    assert "Cheques cannot be recorded on an inactive account." in response.text

    account_page = auth_client.get("/accounts/CK-4200")
    assert account_page.status_code == 200
    assert "Record cheque" not in account_page.text


def test_cheque_withdrawal_rejects_overdraft(auth_client: TestClient):
    page = auth_client.get("/accounts/SV-5500/cheques/new")
    csrf = extract_csrf(page.text)
    response = auth_client.post(
        "/accounts/SV-5500/cheques/new",
        data={
            "csrf_token": csrf,
            "cheque_number": "9",
            "amount": "12000.01",
            "direction": "withdrawal",
        },
    )
    assert response.status_code == 200
    assert "Withdrawal would make the balance negative." in response.text
