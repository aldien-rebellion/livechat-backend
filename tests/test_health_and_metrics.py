import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_health_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # /health
        res1 = await client.get("/health")
        assert res1.status_code == 200
        assert res1.json()["status"] == "ok"

        # /healthcheck
        res2 = await client.get("/healthcheck")
        assert res2.status_code == 200
        assert res2.json()["status"] == "ok"

        # /api/v1/healthcheck
        res3 = await client.get("/api/v1/healthcheck")
        assert res3.status_code == 200
        assert res3.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_metrics_prometheus_exposition():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/metrics")
        assert res.status_code == 200
        assert "text/plain" in res.headers["content-type"]
        body = res.text
        assert "http_requests_total" in body
        assert "websocket_active_connections" in body
        assert "livechat_websocket_active_connections" in body
