
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
import os
from fastapi.responses import RedirectResponse

from app.config.settings import ORIGINS
from app.api.routes import router

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://127.0.0.1:3000").rstrip("/")

app = FastAPI(
    title="Admission Form Digitization API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(router)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    upload_schema = (
        schema.get("components", {})
        .get("schemas", {})
        .get("Body_upload_api_batches__batch_id__upload_post", {})
    )

    files_schema = (
        upload_schema.get("properties", {})
        .get("files", {})
        .get("items", {})
    )

    if files_schema.get("type") == "string":
        files_schema["format"] = "binary"
        files_schema.pop("contentMediaType", None)

    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.get("/")
def root():
    return RedirectResponse(FRONTEND_URL, status_code=307)


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "admission-form-backend",
    }
