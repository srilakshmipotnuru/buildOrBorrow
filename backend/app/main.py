import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import deps_dev, gh_archive, forecast, evaluate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="BuildOrBorrow API",
    description="Backend API for BuildOrBorrow: AI-Powered Build vs Borrow Dependency Evaluator",
    version="1.0.0",
    servers=[
        {"url": "https://buildorborrow-backend-18092420262.us-central1.run.app", "description": "Production Cloud Run Backend"},
        {"url": "http://127.0.0.1:8000", "description": "Local Development Server"}
    ]
)

# Enable CORS for frontend development and public API access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(deps_dev.router, prefix="/api")
app.include_router(gh_archive.router, prefix="/api")
app.include_router(forecast.router, prefix="/api")
app.include_router(evaluate.router, prefix="/api")

@app.get("/")
def root():
    return {
        "status": "healthy",
        "message": "BuildOrBorrow API is running",
        "swagger_docs": "/docs"
    }

