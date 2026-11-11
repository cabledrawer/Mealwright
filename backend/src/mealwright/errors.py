"""Errors the web app can react to: a plain-English `detail` plus a machine-readable `code`.

    {"detail": "There's already an ingredient called Toor dal.", "code": "name_taken", "food_id": 7}

See docs/dev/api-0.2.md section 1.1. Plain HTTPException (just `detail`) is still fine
where the client only shows the message.
"""

from typing import Annotated, Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import AfterValidator


class Problem(Exception):
    def __init__(self, status_code: int, code: str, detail: str, **extra: Any) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail
        self.extra = extra
        # Extra HTTP headers for the answer (e.g. Retry-After); set after making it.
        self.headers: dict[str, str] | None = None


def not_found(what: str = "That") -> Problem:
    return Problem(status.HTTP_404_NOT_FOUND, "not_found", f"{what} isn’t here any more.")


# The biggest and smallest whole numbers the database stores (SQLite: 64 bits).
MOST_STORED = 2**63 - 1
LEAST_STORED = -(2**63)


def _stored(value: int) -> int:
    """Refuse a number the database can't hold. Nothing has such an ID or cursor, and
    passing it on would fail inside the database with a server error.

    Raised as a Problem, not a ValueError: pydantic passes other errors on unchanged, so
    the request gets this 422 at once, wherever in the path, query or body it is."""
    if not LEAST_STORED <= value <= MOST_STORED:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "bad_number", "That number is too big."
        )
    return value


# A whole number from a request that is looked up or stored: an ID, a cursor, a version.
StoredInt = Annotated[int, AfterValidator(_stored)]


def install(app: FastAPI) -> None:
    from mealwright.amounts import MAX_AMOUNT, TooBig
    from mealwright.limits import BodyTooBig, too_big_response

    @app.exception_handler(BodyTooBig)
    async def _body_too_big(_request: Request, error: BodyTooBig) -> JSONResponse:
        return too_big_response(str(error.detail), error.code)

    @app.exception_handler(TooBig)
    async def _too_big(_request: Request, _error: TooBig) -> JSONResponse:
        body = {
            "detail": f"That’s too much: at most {MAX_AMOUNT:,} g, ml or items.",
            "code": "too_big",
        }
        return JSONResponse(body, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT)

    @app.exception_handler(RequestValidationError)
    async def _invalid(_request: Request, error: RequestValidationError) -> JSONResponse:
        # FastAPI's own answer repeats what was sent back (`input`), which fails to be written
        # when it holds a lone surrogate such as "\ud800": a 500 instead of the 422. Where the
        # mistake is and what it is stay; the echo goes.
        shown = [
            {key: value for key, value in one.items() if key not in ("input", "ctx")}
            for one in error.errors()
        ]
        return JSONResponse({"detail": shown}, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT)

    @app.exception_handler(Problem)
    async def _problem(_request: Request, problem: Problem) -> JSONResponse:
        body = {"detail": problem.detail, "code": problem.code, **problem.extra}
        return JSONResponse(body, status_code=problem.status_code, headers=problem.headers)
