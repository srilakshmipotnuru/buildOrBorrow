import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import deps_dev, gh_archive

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="BuildOrBorrow API",
    description="Backend API for BuildOrBorrow: AI-Powered Build vs Borrow Dependency Evaluator",
    version="1.0.0"
)

# Enable CORS for local React / Vite frontend development
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

@app.get("/")
def root():
    return {
        "status": "healthy",
        "message": "BuildOrBorrow API is running",
        "swagger_docs": "http://127.0.0.1:8000/docs"
    }
