"""Version 1 of the HTTP API, mounted at /api/v1."""

from fastapi import APIRouter, Depends

from app.api.deps import verify_csrf
from app.api.v1 import (
    auth,
    dedup,
    google,
    health,
    imports,
    invites,
    projects,
    records,
    setup,
)

# CSRF is checked for every write under /api/v1 (guide 12.1); reads pass straight through.
api_router = APIRouter(dependencies=[Depends(verify_csrf)])
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(google.router)
api_router.include_router(projects.router)
api_router.include_router(setup.router)
api_router.include_router(imports.router)
api_router.include_router(records.router)
api_router.include_router(dedup.router)
api_router.include_router(invites.router)
