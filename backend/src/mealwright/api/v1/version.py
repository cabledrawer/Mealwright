from fastapi import APIRouter
from pydantic import BaseModel

from mealwright import __version__

router = APIRouter(tags=["about"])


class VersionOut(BaseModel):
    version: str


@router.get("/version")
def get_version() -> VersionOut:
    """The running Mealwright version, for update tools such as Diun and Renovate."""
    return VersionOut(version=__version__)
