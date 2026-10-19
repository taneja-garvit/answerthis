import uuid


async def test_create_project(client):
    response = await client.post(
        "/api/projects", json={"title": "  RPM review  ", "description": "Checking claims"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "RPM review"
    assert body["status"] == "ACTIVE"
    assert body["is_demo"] is False
    assert body["drafts"] == []
    assert response.headers["location"] == f"/api/projects/{body['id']}"


async def test_get_project_includes_draft_summaries(client):
    project = (await client.post("/api/projects", json={"title": "P"})).json()
    await client.post(f"/api/projects/{project['id']}/drafts", json={"original_text": "Hello."})
    response = await client.get(f"/api/projects/{project['id']}")
    assert response.status_code == 200
    drafts = response.json()["drafts"]
    assert len(drafts) == 1
    assert drafts[0]["char_count"] == 6
    assert drafts[0]["claim_count"] == 0


async def test_blank_title_rejected(client):
    response = await client.post("/api/projects", json={"title": "   "})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_missing_title_rejected(client):
    response = await client.post("/api/projects", json={})
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["loc"] == ["body", "title"]


async def test_missing_project_returns_404_envelope(client):
    response = await client.get(f"/api/projects/{uuid.uuid4()}")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["message"] == "Project not found"
    assert error["request_id"] == response.headers["x-request-id"]


async def test_invalid_uuid_returns_422(client):
    response = await client.get("/api/projects/not-a-uuid")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_unknown_route_uses_error_envelope(client):
    response = await client.get("/api/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
