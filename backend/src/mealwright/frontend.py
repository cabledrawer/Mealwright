"""Serving the built web app (SvelteKit static build) next to the API.

- Known files are served as they are; `/plan` also finds `plan.html` or `plan/index.html`.
- Any other address (not under /api) gets index.html, so the app's own router takes
  over (single-page app).
- service-worker.js, the manifest and pages are always checked again ("no-cache"), so a new
  version of the app is found promptly (the worker itself never installs one mid-use).
- Files under /_app/immutable/ have content hashes in their names, so browsers may keep
  them for a year. Pages are always checked again.
- Text files are compressed once, at build time (`frontend/scripts/compress.mjs` writes `x.js.br`
  and `x.js.gz` next to `x.js`). A browser that sends `Accept-Encoding` with `br` or `gzip` gets
  that file as it is, with `Content-Encoding` and `Vary: Accept-Encoding`; every other browser, and
  any request for a byte range, gets the plain file. Nothing is compressed while the app runs.
- At start-up, every inline <script> in the built pages is fingerprinted (SHA-256), and
  only those exact scripts are allowed by the Content Security Policy.
"""

import base64
import hashlib
import mimetypes
from html.parser import HTMLParser
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response

from mealwright.compression import accepted_encodings

IMMUTABLE = "_app/immutable/"
# Not every Python knows this one; the installable app's manifest needs it.
MEDIA_TYPES = {".webmanifest": "application/manifest+json"}
FALLBACK = "index.html"


class _InlineScripts(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.scripts: list[str] = []
        self._inside = False
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script" and not any(name == "src" for name, _ in attrs):
            self._inside, self._buffer = True, []

    def handle_data(self, data: str) -> None:
        if self._inside:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._inside:
            self.scripts.append("".join(self._buffer))
            self._inside = False


def inline_script_hashes(folder: Path) -> list[str]:
    """CSP hashes ('sha256-…') of every inline script in the folder's HTML files."""
    hashes: set[str] = set()
    if not folder.is_dir():
        return []
    for page in sorted(folder.rglob("*.html")):
        parser = _InlineScripts()
        parser.feed(page.read_text(encoding="utf-8"))
        for script in parser.scripts:
            digest = hashlib.sha256(script.encode("utf-8")).digest()
            hashes.add("sha256-" + base64.b64encode(digest).decode())
    return sorted(hashes)


def _find(folder: Path, path: str) -> Path | None:
    root = folder.resolve()
    for candidate in (path, f"{path}.html", f"{path}/index.html"):
        target = (root / candidate).resolve()
        # Never serve anything outside the build folder.
        if target.is_relative_to(root) and target.is_file():
            return target
    return None


# The compressed copies the build makes, best first.
ENCODINGS = (("br", ".br"), ("gzip", ".gz"))


def _compressed(found: Path, request: Request) -> tuple[Path, str | None, bool]:
    """The file to send for `found`: its compressed copy when the build made one and the browser
    accepts it. Returns the file, its `Content-Encoding` (None for the plain file) and whether
    the answer depends on what the browser accepts (so it says `Vary: Accept-Encoding`)."""
    copies = [(name, found.with_name(found.name + ext)) for name, ext in ENCODINGS]
    copies = [(name, copy) for name, copy in copies if copy.is_file()]
    if not copies:
        return found, None, False
    if "range" in request.headers:  # a byte range is of the file itself, not of a packed copy
        return found, None, True
    accepted = accepted_encodings(request.headers.get("accept-encoding", ""))
    for name, copy in copies:
        if name in accepted:
            return copy, name, True
    return found, None, True


def mount_frontend(app: FastAPI, folder: Path) -> None:
    """Add the catch-all route for the web app. Call after the API routes."""

    @app.get("/{path:path}", include_in_schema=False)
    def web_app(path: str, request: Request) -> Response:
        if path == "api" or path.startswith("api/") or not folder.is_dir():
            raise HTTPException(404, "Not found")
        found = _find(folder, path.strip("/")) if path.strip("/") else None
        if found is None:
            if "." in path.rsplit("/", 1)[-1]:
                raise HTTPException(404, "Not found")  # a missing file, not a page
            found = folder / FALLBACK
            if not found.is_file():
                raise HTTPException(404, "Not found")
        immutable = path.startswith(IMMUTABLE)
        cache = "public, max-age=31536000, immutable" if immutable else "no-cache"
        sent, encoding, varies = _compressed(found, request)
        headers = {"Cache-Control": cache}
        if encoding is not None:
            headers["Content-Encoding"] = encoding
        if varies:
            headers["Vary"] = "Accept-Encoding"
        return FileResponse(
            sent,
            headers=headers,
            # The type of the file asked for, not of its compressed copy.
            media_type=MEDIA_TYPES.get(found.suffix) or mimetypes.guess_type(found.name)[0],
        )
