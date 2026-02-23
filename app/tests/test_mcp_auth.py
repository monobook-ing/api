from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.mcp.auth import MCP_AUTH_HEADER, MCPHeaderAuthApp


def _client_with_secret(secret: str) -> TestClient:
    app = FastAPI()

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    return TestClient(MCPHeaderAuthApp(app, secret))


def test_mcp_auth_rejects_missing_header():
    client = _client_with_secret("secret-123")

    response = client.get("/ping")

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized MCP request."


def test_mcp_auth_allows_matching_header():
    client = _client_with_secret("secret-123")

    response = client.get("/ping", headers={MCP_AUTH_HEADER: "secret-123"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_mcp_auth_allows_requests_when_secret_disabled():
    client = _client_with_secret("")

    response = client.get("/ping")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
