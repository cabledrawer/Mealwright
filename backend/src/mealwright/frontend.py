"""Serving the built web app (SvelteKit static build) next to the API.

- Known files are served as they are; `/plan` also finds `plan.html` or `plan/index.html`.
- Any other address (not under /api) gets index.html, so the app's own router takes
  over (single-page app).
- Files under /_app/immutable/ have content hashes in their names, so browsers may keep
  them for a year. Pages are always checked again.
- At start-up, every inline <script> in the built pages is fingerprinted (SHA-256), and
  only those exact scripts are allowed by the Content Security Policy.
"""

import base64
import hashlib
from html.parser import HTMLParser
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response

IMMUTABLE = "_app/immutable/"
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
        return FileResponse(found, headers={"Cache-Control": cache})
