import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_submission_returns_202(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/submissions",
        json={
            "submission_ref": "TEST-SUB-001",
            "class_of_business": "property",
            "jurisdiction": "NZ",
        },
    )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "RECEIVED"
    assert data["submission_ref"] == "TEST-SUB-001"
    assert "submission_id" in data


@pytest.mark.asyncio
async def test_get_submission_returns_404_for_unknown(client: AsyncClient) -> None:
    response = await client.get("/api/v1/submissions/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_submission_returns_created_record(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/api/v1/submissions",
        json={
            "submission_ref": "TEST-SUB-002",
            "class_of_business": "property",
            "jurisdiction": "AU",
        },
    )
    submission_id = create_resp.json()["submission_id"]

    get_resp = await client.get(f"/api/v1/submissions/{submission_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["submission_ref"] == "TEST-SUB-002"
    assert data["jurisdiction"] == "AU"
