from fastapi.testclient import TestClient


def test_inclusive_january_2026_dates(auth_client: TestClient):
    response = auth_client.get(
        "/accounts/LN-1001",
        params={"start_date": "2026-01-20", "end_date": "2026-01-20"},
    )
    assert response.status_code == 200
    assert "TX-LN-1001-F02" in response.text
    assert "FIXTURE exact $500.00" in response.text
    assert "TX-LN-1001-F05" not in response.text
    assert "TX-LN-1001-F06" not in response.text


def test_date_outside_january_2026(auth_client: TestClient):
    inside = auth_client.get(
        "/accounts/LN-1001",
        params={"start_date": "2026-01-01", "end_date": "2026-01-31", "min_amount": "1199"},
    )
    assert "TX-LN-1001-F07" in inside.text
    outside = auth_client.get(
        "/accounts/LN-1001",
        params={"start_date": "2025-12-15", "end_date": "2025-12-15"},
    )
    assert "TX-LN-1001-F05" in outside.text
    assert "FIXTURE $500.01 credit — outside January 2026" in outside.text


def test_strictly_greater_than_500_excludes_exact_amount(auth_client: TestClient):
    response = auth_client.get(
        "/accounts/LN-1001",
        params={
            "start_date": "2026-01-20",
            "end_date": "2026-01-25",
            "min_amount": "500",
        },
    )
    assert "TX-LN-1001-F02" not in response.text
    assert "FIXTURE exact $500.00" not in response.text
    assert "TX-LN-1001-F03" in response.text
    assert "FIXTURE above $500.00" in response.text


def test_reversed_date_range_is_rejected(auth_client: TestClient):
    response = auth_client.get(
        "/accounts/LN-1001",
        params={"start_date": "2026-02-01", "end_date": "2026-01-01"},
    )
    assert "End date must be on or after the start date." in response.text
    assert "View Transaction" not in response.text


def test_non_numeric_amount_is_rejected(auth_client: TestClient):
    response = auth_client.get("/accounts/LN-1001", params={"min_amount": "abc"})
    assert "Enter a valid amount." in response.text


def test_pagination_keeps_ten_rows_and_preserves_filters(auth_client: TestClient):
    page1 = auth_client.get("/accounts/CK-1001")
    assert "Showing 1–10 of 620 transactions." in page1.text
    page2 = auth_client.get("/accounts/CK-1001", params={"page": "2"})
    assert "Showing 11–20 of 620 transactions." in page2.text
    assert "Page 2 of 62" in page2.text

    filtered = auth_client.get(
        "/accounts/LN-1001",
        params={"start_date": "2026-01-20", "end_date": "2026-01-20"},
    )
    assert 'id="start_date"' in filtered.text
    assert 'value="2026-01-20"' in filtered.text
    assert "View Transaction" in filtered.text


def test_empty_account_and_inactive_account(auth_client: TestClient):
    empty = auth_client.get("/accounts/SV-5500")
    assert "No transactions for this account." in empty.text
    inactive = auth_client.get("/accounts/CK-4200")
    assert "inactive" in inactive.text
    assert "View Transaction" in inactive.text
