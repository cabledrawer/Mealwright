"""Errors the web app can react to: a plain-English `detail` plus a machine-readable `code`.

    {"detail": "There's already an ingredient called Toor dal.", "code": "name_taken", "food_id": 7}

See docs/dev/api-endpoints.md section 1.1: one status and one `code` per situation, and every
error answer is this shape (0.9.5-beta.3, D2). A plain HTTPException raised anywhere (FastAPI's
own 404 and 405 too) is answered in it by `install`, and validation errors carry `invalid`.
Sentences said in more than one place live here, once.
"""

from typing import Annotated, Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import AfterValidator
from starlette.exceptions import HTTPException


class Problem(Exception):
    def __init__(self, status_code: int, code: str, detail: str, **extra: Any) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail
        self.extra = extra
        # Extra HTTP headers for the answer (e.g. Retry-After); set after making it.
        self.headers: dict[str, str] | None = None


# The sentences more than one route says (BE30: one constant per sentence, imported).
SIGN_IN = "Please sign in."
ADMINS_ONLY = "Only the household’s admin can change this."
OTHER_SITE = "This request came from another site."
ALREADY_SET_UP = "Mealwright is already set up."
WRONG_PASSWORD = "That isn’t your current password."  # noqa: S105  # nosec B105 (words)
NOTHING_TO_CHANGE = "There’s nothing to change."  # proposed, for cabledrawer
CANT_DO_HERE = "That can’t be done here."  # an unknown method on a known path; proposed


def not_found(what: str = "That") -> Problem:
    """The one 404: no such thing in this household (an id from another household too, so an
    answer never tells the two apart). "Exists, but not in that state" is a 409 instead."""
    return Problem(status.HTTP_404_NOT_FOUND, "not_found", f"{what} isn’t here any more.")


def signed_out() -> Problem:
    """Not signed in, or the sign-in has ended: 401 `signed_out`, wherever it is noticed."""
    return Problem(status.HTTP_401_UNAUTHORIZED, "signed_out", SIGN_IN)


def admins_only() -> Problem:
    return Problem(status.HTTP_403_FORBIDDEN, "admins_only", ADMINS_ONLY)


def wrong_password() -> Problem:
    """A person's own current password, typed again to confirm something, is wrong. 403: they are
    signed in but may not do this without it (sign-in itself is 401 `wrong_sign_in`)."""
    return Problem(status.HTTP_403_FORBIDDEN, "wrong_password", WRONG_PASSWORD)


def password_length(detail: str) -> Problem:
    """A password too short or too long for what it is for (each says its own range)."""
    return Problem(status.HTTP_422_UNPROCESSABLE_CONTENT, "password_length", detail)


def nothing_to_change(detail: str = NOTHING_TO_CHANGE) -> Problem:
    """The request names nothing to change (an empty PATCH). One of two codes for it; the other,
    `one_field`, is for a route that takes exactly one field at a time."""
    return Problem(status.HTTP_422_UNPROCESSABLE_CONTENT, "nothing_to_change", detail)


def already_there(detail: str) -> Problem:
    """It is already so: moving something where it already is, freezing what is frozen, adding a
    name it already has. 409, with the sentence of the route."""
    return Problem(status.HTTP_409_CONFLICT, "already_there", detail)


def name_taken(detail: str, **existing: Any) -> Problem:
    """A new or renamed thing would have a name the household already uses (ignoring case and
    accents). 409 `name_taken`, carrying the one that has it so the screen can pick it."""
    return Problem(status.HTTP_409_CONFLICT, "name_taken", detail, **existing)


# The code FastAPI's own errors (and any plain HTTPException) get, by status.
_PLAIN_CODES = {
    400: "bad_request",
    401: "signed_out",
    403: "refused",
    404: "not_found",
    405: "cant_do_here",
    413: "body_too_big",
    503: "busy",
}


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
        return JSONResponse(
            {"detail": shown, "code": "invalid"}, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT
        )

    @app.exception_handler(HTTPException)
    async def _plain(_request: Request, error: HTTPException) -> JSONResponse:
        # FastAPI's own 404 ("Not Found") and 405, and any plain HTTPException left: the same
        # shape as every other error, with a code and a sentence a person can read.
        code = _PLAIN_CODES.get(error.status_code, "error")
        detail = str(error.detail)
        if error.status_code == status.HTTP_404_NOT_FOUND:
            detail = not_found().detail
        elif error.status_code == status.HTTP_405_METHOD_NOT_ALLOWED:
            detail = CANT_DO_HERE
        return JSONResponse(
            {"detail": detail, "code": code},
            status_code=error.status_code,
            headers=getattr(error, "headers", None),
        )

    @app.exception_handler(Problem)
    async def _problem(_request: Request, problem: Problem) -> JSONResponse:
        body = {"detail": problem.detail, "code": problem.code, **problem.extra}
        return JSONResponse(body, status_code=problem.status_code, headers=problem.headers)
