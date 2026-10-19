import uuid

import httpx

from app.db.session import Database, create_engine_from_url
from app.main import create_app
from tests.conftest import make_settings

UNREACHABLE = "postgresql://nobody:hunter2-secret@127.0.0.1:1/nowhere"


async def test_health_ok(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}


async def test_request_id_generated_and_returned(client):
    response = await client.get("/health")
    assert len(response.headers["x-request-id"]) == 32


async def test_well_formed_request_id_is_echoed(client):
    response = await client.get("/health", headers={"X-Request-ID": "trace-abc_123"})
    assert response.headers["x-request-id"] == "trace-abc_123"


async def test_malformed_request_id_is_replaced(client):
    response = await client.get("/health", headers={"X-Request-ID": "bad id\x00<script>"})
    assert response.headers["x-request-id"] != "bad id\x00<script>"


async def _unreachable_client() -> tuple[httpx.AsyncClient, Database]:
    settings = make_settings(UNREACHABLE, db_connect_timeout_seconds=2)
    database = Database(create_engine_from_url(UNREACHABLE, settings))
    app = create_app(settings, database)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t"), database


async def test_health_degraded_when_database_unreachable_and_leaks_nothing():
    http, database = await _unreachable_client()
    async with http:
        response = await http.get("/health")
    await database.dispose()
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unavailable"}
    assert "hunter2" not in response.text and "127.0.0.1" not in response.text


async def test_api_returns_503_envelope_when_database_unreachable():
    http, database = await _unreachable_client()
    async with http:
        response = await http.get(f"/api/projects/{uuid.uuid4()}")
    await database.dispose()
    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "database_unavailable"
    assert body["error"]["request_id"] == response.headers["x-request-id"]
    assert "hunter2" not in response.text and "nowhere" not in response.text


async def test_cors_allows_configured_origin_only(client):
    allowed = await client.options(
        "/api/projects",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    denied = await client.options(
        "/api/projects",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in denied.headers
