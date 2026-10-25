from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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

# 3. FastAPI Route
@app.get("/health", response_model=HealthCheckResponse)
async def health_check():
    return {"status": "ok", "message": "Backend Core is running"}