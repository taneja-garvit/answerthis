import uuid

import pytest


@pytest.fixture
async def project_id(client) -> str:
    return (await client.post("/api/projects", json={"title": "Draft tests"})).json()["id"]


async def test_create_draft(client, project_id):
    response = await client.post(
        f"/api/projects/{project_id}/drafts", json={"original_text": "  RPM reduced deaths. "}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["original_text"] == "RPM reduced deaths."
    assert body["char_count"] == len("RPM reduced deaths.")
    assert body["project_id"] == project_id
    fetched = await client.get(f"/api/drafts/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]


@pytest.mark.parametrize("text", ["", "   \n\t "])
async def test_empty_draft_rejected(client, project_id, text):
    response = await client.post(f"/api/projects/{project_id}/drafts", json={"original_text": text})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "draft_empty"


async def test_oversized_draft_rejected(client, project_id, settings):
    text = "x" * (settings.max_draft_chars + 1)
    response = await client.post(f"/api/projects/{project_id}/drafts", json={"original_text": text})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "draft_too_large"


async def test_draft_at_limit_accepted(client, project_id, settings):
    text = "x" * settings.max_draft_chars
    response = await client.post(f"/api/projects/{project_id}/drafts", json={"original_text": text})
    assert response.status_code == 201


async def test_hard_cap_rejected_without_echoing_input(client, project_id):
    text = "secret-draft-" * 20_000
    response = await client.post(f"/api/projects/{project_id}/drafts", json={"original_text": text})
    assert response.status_code == 422
    assert "secret-draft-" not in response.text


async def test_missing_original_text_rejected(client, project_id):
    response = await client.post(f"/api/projects/{project_id}/drafts", json={})
    assert response.status_code == 422


async def test_draft_for_missing_project_returns_404(client):
    response = await client.post(
        f"/api/projects/{uuid.uuid4()}/drafts", json={"original_text": "Text."}
    )
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Project not found"


async def test_missing_draft_returns_404(client):
    assert (await client.get(f"/api/drafts/{uuid.uuid4()}")).status_code == 404
    assert (await client.get(f"/api/drafts/{uuid.uuid4()}/claims")).status_code == 404


async def test_invalid_draft_id_returns_422(client):
    assert (await client.get("/api/drafts/123/claims")).status_code == 422
