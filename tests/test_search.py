from fastapi.testclient import TestClient


def test_exact_member_id_preserves_leading_zeros(auth_client: TestClient):
    response = auth_client.get("/members?q=001234")
    assert response.status_code == 200
    assert "001234" in response.text
    assert "Elena Vargas" in response.text
    assert response.text.count("View Member") == 1


def test_partial_name_and_similar_matches(auth_client: TestClient):
    elena = auth_client.get("/members?q=Elena")
    assert "Elena Vargas" in elena.text
    assert "Elena Varga" in elena.text
    assert "001234" in elena.text
    assert "001235" in elena.text

    james = auth_client.get("/members?q=James")
    assert "James Okonkwo" in james.text
    assert "James Okoye" in james.text


def test_full_name_search(auth_client: TestClient):
    response = auth_client.get("/members?q=Elena+Vargas")
    assert "Elena Vargas" in response.text
    assert 'data-testid="member-row-001234"' in response.text
    assert 'data-testid="member-row-001235"' not in response.text


def test_no_matches(auth_client: TestClient):
    response = auth_client.get("/members?q=zzzz-no-such-member")
    assert response.status_code == 200
    assert "No members match that search." in response.text


def test_empty_input_validation(auth_client: TestClient):
    response = auth_client.get("/members?q=")
    assert "Enter a member ID or name to search." in response.text
    assert "View Member" not in response.text
