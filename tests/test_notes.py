from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import InvestigationNote
from tests.conftest import extract_csrf


def _create_note(client: TestClient, transaction_id: str, body: str, category: str = "general review"):
    form = client.get(f"/transactions/{transaction_id}/notes/new")
    assert form.status_code == 200
    token_match = __import__("re").search(r'name="idempotency_token"\s+value="([^"]+)"', form.text)
    assert token_match
    token = token_match.group(1)
    review = client.post(
        f"/transactions/{transaction_id}/notes/review",
        data={
            "csrf_token": extract_csrf(form.text),
            "idempotency_token": token,
            "body": body,
            "category": category,
        },
        follow_redirects=True,
    )
    assert review.status_code == 200
    assert "Review investigation note" in review.text
    confirm = client.post(
        f"/transactions/{transaction_id}/notes/confirm",
        data={
            "csrf_token": extract_csrf(review.text),
            "idempotency_token": token,
            "body": body,
            "category": category,
        },
        follow_redirects=True,
    )
    return token, confirm


def test_note_persists_with_author_and_timestamp(auth_client: TestClient):
    _token, success = _create_note(
        auth_client,
        "TX-LN-1001-F01",
        "Member recognized this $250.00 January debit.",
        "customer explanation",
    )
    assert success.status_code == 200
    assert "Investigation note saved" in success.text
    assert "Jordan Patel" in success.text
    assert "UTC" in success.text
    assert "customer explanation" in success.text
    assert "NT-" in success.text

    txn = auth_client.get("/transactions/TX-LN-1001-F01")
    assert "Member recognized this $250.00 January debit." in txn.text
    assert "Jordan Patel" in txn.text


def test_duplicate_token_does_not_create_second_row(auth_client: TestClient, db_path):
    token, success = _create_note(auth_client, "TX-LN-1001-F04", "First save of this review.")
    assert success.status_code == 200
    csrf_page = auth_client.get("/transactions/TX-LN-1001-F04")
    replay = auth_client.post(
        "/transactions/TX-LN-1001-F04/notes/confirm",
        data={
            "csrf_token": extract_csrf(csrf_page.text) if "csrf_token" in csrf_page.text else extract_csrf(
                auth_client.get("/transactions/TX-LN-1001-F04/notes/new").text
            ),
            "idempotency_token": token,
            "body": "First save of this review.",
            "category": "general review",
        },
        follow_redirects=True,
    )
    assert replay.status_code == 200
    assert "Investigation note saved" in replay.text

    db = SessionLocal()
    try:
        count = db.scalar(
            select(func.count()).select_from(InvestigationNote).where(
                InvestigationNote.idempotency_token == token
            )
        )
        body_count = db.scalar(
            select(func.count()).select_from(InvestigationNote).where(
                InvestigationNote.body == "First save of this review."
            )
        )
        assert count == 1
        assert body_count == 1
    finally:
        db.close()


def test_uncertain_note_retry_does_not_duplicate(auth_client: TestClient):
    scenarios = auth_client.get("/dev/scenarios")
    auth_client.post(
        "/dev/scenarios",
        data={"csrf_token": extract_csrf(scenarios.text), "action": "uncertain-note"},
        follow_redirects=True,
    )
    form = auth_client.get("/transactions/TX-LN-1001-F06/notes/new")
    token = __import__("re").search(r'name="idempotency_token"\s+value="([^"]+)"', form.text).group(1)
    body = "Retry-safe note for the February fixture."
    review = auth_client.post(
        "/transactions/TX-LN-1001-F06/notes/review",
        data={
            "csrf_token": extract_csrf(form.text),
            "idempotency_token": token,
            "body": body,
            "category": "follow-up required",
        },
    )
    interrupted = auth_client.post(
        "/transactions/TX-LN-1001-F06/notes/confirm",
        data={
            "csrf_token": extract_csrf(review.text),
            "idempotency_token": token,
            "body": body,
            "category": "follow-up required",
        },
    )
    assert interrupted.status_code == 200
    assert "Confirmation interrupted" in interrupted.text
    retry = auth_client.post(
        "/transactions/TX-LN-1001-F06/notes/confirm",
        data={
            "csrf_token": extract_csrf(interrupted.text),
            "idempotency_token": token,
            "body": body,
            "category": "follow-up required",
        },
        follow_redirects=True,
    )
    assert "Investigation note saved" in retry.text
    txn = auth_client.get("/transactions/TX-LN-1001-F06")
    assert txn.text.count(body) == 1
