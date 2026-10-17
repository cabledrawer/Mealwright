"""Errors the web app can react to: a plain-English `detail` plus a machine-readable `code`.

    {"detail": "There's already a food called Toor dal.", "code": "name_taken", "food_id": 7}

See docs/dev/api-0.2.md section 1.1. Plain HTTPException (just `detail`) is still fine
where the client only shows the message.
"""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class Problem(Exception):
    def __init__(self, status_code: int, code: str, detail: str, **extra: Any) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail
        self.extra = extra


def not_found(what: str = "That") -> Problem:
    return Problem(status.HTTP_404_NOT_FOUND, "not_found", f"{what} isn't here any more.")


def install(app: FastAPI) -> None:
    @app.exception_handler(Problem)
    async def _problem(_request: Request, problem: Problem) -> JSONResponse:
        body = {"detail": problem.detail, "code": problem.code, **problem.extra}
        return JSONResponse(body, status_code=problem.status_code)
