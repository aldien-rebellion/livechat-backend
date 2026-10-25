from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.controllers.auth_controller import router as auth_router
from app.controllers.websocket_controller import router as websocket_router, manager
from app.controllers.search_controller import router as search_router

app = FastAPI(title="LiveChat Backend API")

# 1. CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Pydantic v2 Schema for Health Check
class HealthCheckResponse(BaseModel):
    status: str
    message: str

# 3. Health Routes
@app.get("/health", response_model=HealthCheckResponse)
@app.get("/healthcheck", response_model=HealthCheckResponse)
@app.get("/api/v1/health", response_model=HealthCheckResponse)
@app.get("/api/v1/healthcheck", response_model=HealthCheckResponse)
async def health_check():
    return {"status": "ok", "message": "Backend Core is running"}

# 4. Prometheus Metrics Scrape Endpoint
@app.get("/metrics")
async def metrics():
    active_ws = sum(len(conns) for conns in manager.active_connections.values())
    metrics_text = (
        "# HELP http_requests_total Total HTTP requests\n"
        "# TYPE http_requests_total counter\n"
        'http_requests_total{status="200",handler="/health"} 1\n'
        "# HELP websocket_active_connections Current active WebSocket connections\n"
        "# TYPE websocket_active_connections gauge\n"
        f"websocket_active_connections {active_ws}\n"
        f"livechat_websocket_active_connections {active_ws}\n"
    )
    return Response(content=metrics_text, media_type="text/plain; version=0.0.4")

# 5. Include Application Routers
app.include_router(auth_router, prefix="/api/v1")
app.include_router(auth_router)
app.include_router(search_router, prefix="/api/v1")
app.include_router(search_router)
app.include_router(websocket_router)
