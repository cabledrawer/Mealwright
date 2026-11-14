"""The container's health check (0.9.5): `GET /health` says "ok" only when the database
answers a trivial query, not just because the process is up.

No sign-in: the image's HEALTHCHECK calls it from inside the container. It reveals nothing:
no version, no counts, no names, and no reason for a failure (503 with the same short body
whatever went wrong; the reason goes to the log). `GET /version` stays as it was, for Diun and
Renovate and for the web app's own "is the server there" check.
"""

import logging
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from mealwright.auth import Db

log = logging.getLogger(__name__)

router = APIRouter(tags=["about"])


class HealthOut(BaseModel):
    status: Literal["ok", "unavailable"]


@router.get("/health", response_model=HealthOut, responses={503: {"model": HealthOut}})
def get_health(db: Db) -> HealthOut | JSONResponse:
    """Ok when the database answers `SELECT 1`; 503 when it doesn't."""
    try:
        db.execute(text("SELECT 1")).scalar_one()
    except Exception:
        log.exception("health check: the database did not answer")
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return HealthOut(status="ok")
