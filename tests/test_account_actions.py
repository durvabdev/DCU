from fastapi.testclient import TestClient

from tests.conftest import extract_csrf


def test_credit_via_cheque_updates_balance_and_creates_txn(auth_client: TestClient):
    from app.database import SessionLocal
    from app.models import Account, Transaction

    db = SessionLocal()
    try:
        account = db.get(Account, "CK-1001")
        assert account is not None
        before = account.balance_cents
    finally:
        db.close()

    page = auth_client.get("/accounts/CK-1001")
    assert page.status_code == 200
    assert 'href="/accounts/CK-1001/credit"' in page.text
    assert 'href="/accounts/CK-1001/debit"' in page.text

    form = auth_client.get("/accounts/CK-1001/credit")
    assert form.status_code == 200
    csrf = extract_csrf(form.text)
    response = auth_client.post(
        "/accounts/CK-1001/credit",
        data={
            "csrf_token": csrf,
            "method": "cheque",
            "cheque_number": "4412",
            "amount": "50.00",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/accounts/CK-1001")
    assert "flash=" in location

    after = auth_client.get(location)
    assert after.status_code == 200
    assert 'class="alert alert-success"' in after.text
    assert "Credited $50.00." in after.text
    assert "TX-CK-1001-" in after.text

    db = SessionLocal()
    try:
        account = db.get(Account, "CK-1001")
        assert account is not None
        assert account.balance_cents == before + 5000
        txn = (
            db.query(Transaction)
            .filter(
                Transaction.account_id == "CK-1001",
                Transaction.description == "Cheque credit #4412",
            )
            .one()
        )
        assert txn.direction == "credit"
        assert txn.amount_cents == 5000
        assert txn.status == "posted"
    finally:
        db.close()


def test_debit_via_cheque_overdraft_rejected(auth_client: TestClient):
    from app.database import SessionLocal
    from app.models import Account

    db = SessionLocal()
    try:
        account = db.get(Account, "CK-1001")
        assert account is not None
        account.balance_cents = 2500
        db.commit()
        before = account.balance_cents
    finally:
        db.close()

    form = auth_client.get("/accounts/CK-1001/debit")
    csrf = extract_csrf(form.text)
    response = auth_client.post(
        "/accounts/CK-1001/debit",
        data={
            "csrf_token": csrf,
            "method": "cheque",
            "cheque_number": "99",
            "amount": "50.00",
        },
    )
    assert response.status_code == 200
    assert "This debit would make the account balance negative." in response.text

    db = SessionLocal()
    try:
        account = db.get(Account, "CK-1001")
        assert account is not None
        assert account.balance_cents == before
    finally:
        db.close()


def test_transfer_credit_moves_money_between_accounts(auth_client: TestClient):
    from app.database import SessionLocal
    from app.models import Account, Transaction

    db = SessionLocal()
    try:
        ck = db.get(Account, "CK-1001")
        other = db.get(Account, "CK-2001")
        assert ck is not None and other is not None
        ck_before = ck.balance_cents
        other_before = other.balance_cents
    finally:
        db.close()

    form = auth_client.get("/accounts/CK-1001/credit")
    csrf = extract_csrf(form.text)
    response = auth_client.post(
        "/accounts/CK-1001/credit",
        data={
            "csrf_token": csrf,
            "method": "transfer",
            "counterparty_id": "CK-2001",
            "amount": "25.00",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    after = auth_client.get(location)
    assert "Credited $25.00 via transfer" in after.text
    assert "TX-CK-2001-" in after.text
    assert "TX-CK-1001-" in after.text

    db = SessionLocal()
    try:
        ck = db.get(Account, "CK-1001")
        other = db.get(Account, "CK-2001")
        assert ck is not None and other is not None
        assert ck.balance_cents == ck_before + 2500
        assert other.balance_cents == other_before - 2500
        debit = (
            db.query(Transaction)
            .filter(
                Transaction.account_id == "CK-2001",
                Transaction.description == "Transfer to CK-1001",
            )
            .one()
        )
        credit = (
            db.query(Transaction)
            .filter(
                Transaction.account_id == "CK-1001",
                Transaction.description == "Transfer from CK-2001",
            )
            .one()
        )
        assert debit.direction == "debit" and debit.amount_cents == 2500
        assert credit.direction == "credit" and credit.amount_cents == 2500
    finally:
        db.close()


def test_transfer_debit_moves_money_between_accounts(auth_client: TestClient):
    from app.database import SessionLocal
    from app.models import Account, Transaction

    db = SessionLocal()
    try:
        ck = db.get(Account, "CK-1001")
        other = db.get(Account, "SV-5500")
        assert ck is not None and other is not None
        ck_before = ck.balance_cents
        other_before = other.balance_cents
    finally:
        db.close()

    form = auth_client.get("/accounts/CK-1001/debit")
    csrf = extract_csrf(form.text)
    response = auth_client.post(
        "/accounts/CK-1001/debit",
        data={
            "csrf_token": csrf,
            "method": "transfer",
            "counterparty_id": "SV-5500",
            "amount": "10.00",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    after = auth_client.get(response.headers["location"])
    assert "Debited $10.00 via transfer" in after.text

    db = SessionLocal()
    try:
        ck = db.get(Account, "CK-1001")
        other = db.get(Account, "SV-5500")
        assert ck is not None and other is not None
        assert ck.balance_cents == ck_before - 1000
        assert other.balance_cents == other_before + 1000
        assert (
            db.query(Transaction)
            .filter(
                Transaction.account_id == "CK-1001",
                Transaction.description == "Transfer to SV-5500",
            )
            .count()
            == 1
        )
        assert (
            db.query(Transaction)
            .filter(
                Transaction.account_id == "SV-5500",
                Transaction.description == "Transfer from CK-1001",
            )
            .count()
            == 1
        )
    finally:
        db.close()


def test_same_account_transfer_rejected(auth_client: TestClient):
    form = auth_client.get("/accounts/CK-1001/credit")
    csrf = extract_csrf(form.text)
    response = auth_client.post(
        "/accounts/CK-1001/credit",
        data={
            "csrf_token": csrf,
            "method": "transfer",
            "counterparty_id": "CK-1001",
            "amount": "5.00",
        },
    )
    assert response.status_code == 200
    assert "Counterparty account must be different from this account." in response.text


def test_credit_debit_requires_csrf(auth_client: TestClient):
    response = auth_client.post(
        "/accounts/CK-1001/credit",
        data={
            "csrf_token": "invalid",
            "method": "cheque",
            "cheque_number": "1",
            "amount": "1.00",
        },
    )
    assert response.status_code == 403
    assert "This form could not be verified." in response.text


def test_credit_debit_blocked_on_inactive_account(auth_client: TestClient):
    page = auth_client.get("/accounts/CK-4200")
    assert page.status_code == 200
    assert 'href="/accounts/CK-4200/credit"' not in page.text
    assert 'href="/accounts/CK-4200/debit"' not in page.text
    assert 'href="/accounts/CK-4200/close"' not in page.text

    for path in ("/accounts/CK-4200/credit", "/accounts/CK-4200/debit"):
        response = auth_client.get(path)
        assert response.status_code == 403
        assert "Credits and debits can only be posted on active accounts." in response.text


def test_close_account_requires_zero_balance(auth_client: TestClient):
    page = auth_client.get("/accounts/CK-1001")
    assert 'href="/accounts/CK-1001/close"' in page.text

    form = auth_client.get("/accounts/CK-1001/close")
    assert form.status_code == 200
    assert "Bring the current balance to $0.00 before closing." in form.text
    assert 'data-testid="confirm-close"' not in form.text


def test_close_account_sets_inactive(auth_client: TestClient):
    open_page = auth_client.get("/members/001234/accounts/new")
    csrf = extract_csrf(open_page.text)
    opened = auth_client.post(
        "/members/001234/accounts/new",
        data={"csrf_token": csrf, "account_type": "checking"},
        follow_redirects=False,
    )
    assert opened.status_code == 303
    account_id = "CK-1002"

    form = auth_client.get(f"/accounts/{account_id}/close")
    assert form.status_code == 200
    csrf = extract_csrf(form.text)
    response = auth_client.post(
        f"/accounts/{account_id}/close",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith(f"/accounts/{account_id}")
    assert "flash=" in location

    after = auth_client.get(location)
    assert after.status_code == 200
    assert f"Account {account_id} closed." in after.text
    assert "badge-inactive" in after.text
    assert 'href="/accounts/CK-1002/credit"' not in after.text
    assert 'href="/accounts/CK-1002/close"' not in after.text


def test_close_account_blocked_when_already_inactive(auth_client: TestClient):
    response = auth_client.get("/accounts/CK-4200/close")
    assert response.status_code == 403
    assert "Only active accounts can be closed." in response.text


def test_close_account_requires_csrf(auth_client: TestClient):
    open_page = auth_client.get("/members/005500/accounts/new")
    csrf = extract_csrf(open_page.text)
    auth_client.post(
        "/members/005500/accounts/new",
        data={"csrf_token": csrf, "account_type": "checking"},
        follow_redirects=False,
    )
    response = auth_client.post(
        "/accounts/CK-5501/close",
        data={"csrf_token": "wrong"},
    )
    assert response.status_code == 403
    assert "This form could not be verified." in response.text


def test_account_lookup_finds_ck_1001(auth_client: TestClient):
    home = auth_client.get("/")
    assert 'href="/accounts"' in home.text

    response = auth_client.get("/accounts?q=CK-1001")
    assert response.status_code == 200
    assert 'data-testid="account-row-CK-1001"' in response.text
    assert "Elena Vargas" in response.text
    assert "View Account" in response.text
    assert 'href="/accounts/CK-1001"' in response.text


def test_account_lookup_no_match(auth_client: TestClient):
    response = auth_client.get("/accounts?q=ZZ-9999")
    assert response.status_code == 200
    assert "No accounts match that search." in response.text


def test_account_lookup_empty_input(auth_client: TestClient):
    response = auth_client.get("/accounts?q=")
    assert "Enter an account ID to search." in response.text
    assert "View Account" not in response.text
