from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes import router
from routes.mock_apis import router as mock_apis_router

app = FastAPI(title="TeleSight API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.include_router(mock_apis_router, prefix="/mock-api")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "TeleSight API"}
