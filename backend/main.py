from fastapi import FastAPI

app = FastAPI(
    title="BuildOrBorrow API",
    description="Backend API for BuildOrBorrow",
    version="0.1.0",
)


@app.get("/")
def root():
    return {
        "message": "BuildOrBorrow API is running"
    }


@app.get("/health")
def health():
    return {
        "status": "ok"
    }