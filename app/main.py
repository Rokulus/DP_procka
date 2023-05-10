"""Main FastAPI app instance declaration."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.api import api_router
from app.core import config

tags_metadata = [
    {
        "name": "Authorization",
        "description": "Operations with tokens"
    },
    {
        "name": "Users",
        "description": "Operations with user"
    },
    {
        "name": "FMU Javascript",
        "description": "Operations with convertion to FMU javascript files",
        "externalDocs": {
            "description": "Site with models",
            "url": "https://apis.iolab.sk/fmuJS/model-info",
        },
    },
    {
        "name": "FMU",
        "description": "Operations with FMU files",
    },
    {
        "name": "Matlab",
        "description": "Operations with Matlab",
        "externalDocs": {
            "description": "Websocket",
            "url": "https://apis.iolab.sk/matlab/websocket/site",
        },
    },
        {
        "name": "Logs",
        "description": "Get error logs. Only super users can access this endpoint.",
    },
]

app = FastAPI(
    title=config.settings.PROJECT_NAME,
    version=config.settings.VERSION,
    description=config.settings.DESCRIPTION,
    openapi_url="/openapi.json",
    docs_url="/",
    openapi_tags=tags_metadata,
)

app.mount("/static", StaticFiles(directory="static"), name="assets")

app.include_router(api_router)

# Sets all CORS enabled origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(origin) for origin in config.settings.BACKEND_CORS_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Guards against HTTP Host Header attacks
app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.settings.ALLOWED_HOSTS)
