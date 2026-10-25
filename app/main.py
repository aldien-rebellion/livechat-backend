from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.controllers.auth_controller import router as auth_router
from app.controllers.websocket_controller import router as websocket_router

app = FastAPI(title="LiveChat Backend API")

# 1. CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Pydantic v2 Schema ตัวอย่างสำหรับ Health Check
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

# 4. Include Application Routers
app.include_router(auth_router, prefix="/api/v1")
app.include_router(auth_router)
app.include_router(websocket_router)
