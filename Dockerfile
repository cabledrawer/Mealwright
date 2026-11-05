# syntax=docker/dockerfile:1
# Mealwright: one container serving the API and the web app (spec section 3).
# Base images are pinned by digest; change them on purpose, in their own commit.

# --- 1. Build the web app ---------------------------------------------------------------
FROM node:24-trixie-slim@sha256:7f486cabe892bff8fef04c0f7da8dba84a560be3e4e2740b7a86afc57ebec315 AS web
ENV NPM_CONFIG_UPDATE_NOTIFIER=false NPM_CONFIG_FUND=false NPM_CONFIG_AUDIT=false
WORKDIR /src/frontend
# The libraries first, from the package files alone: this layer is reused until a library
# changes, so a change to the app's own code doesn't install them all again.
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci
COPY frontend/ ./
# The app shows its own version (written in at build time); the version lives in one place.
COPY backend/pyproject.toml /src/backend/pyproject.toml
RUN npm run build

# --- 2. Install the backend into a virtual environment ----------------------------------
FROM python:3.14-slim-trixie@sha256:af8a5aa14780025dbfbcfbc81bd8a91ebd87711dd5b0f48ed71090949dd7cb1d AS api
COPY --from=ghcr.io/astral-sh/uv:0.13.1@sha256:4a1f3666816dafadd20ceb71eac9a7d56d7ef30279f7d64048519ab901ada336 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_NO_CACHE=1
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
# Pillow is only ever installed from its ready-made wheel (amd64 and arm64), never built
# here from source: if no wheel fits, the build stops.
RUN uv sync --frozen --no-dev --no-install-project --no-build-package pillow
COPY backend/ ./
RUN uv sync --frozen --no-dev --no-editable --no-build-package pillow

# --- 3. The image that runs --------------------------------------------------------------
FROM python:3.14-slim-trixie@sha256:af8a5aa14780025dbfbcfbc81bd8a91ebd87711dd5b0f48ed71090949dd7cb1d
LABEL org.opencontainers.image.title="Mealwright" \
      org.opencontainers.image.description="Self-hosted meal planning, pantry and shopping." \
      org.opencontainers.image.licenses="AGPL-3.0-only"
# A user with no login and no home folder; everything Mealwright keeps lives in /data.
# pip isn't needed at run time (uv installed everything above), and it carries its own
# copies of other libraries, so remove it.
RUN python -m pip uninstall --yes --quiet pip \
 && groupadd --system --gid 10001 mealwright \
 && useradd --system --uid 10001 --gid mealwright --no-create-home \
      --home-dir /nonexistent --shell /usr/sbin/nologin mealwright \
 && mkdir /data && chown mealwright:mealwright /data
COPY --from=api /app/backend/.venv /app/backend/.venv
COPY --from=web /src/frontend/build /app/frontend
ENV PATH=/app/backend/.venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MEALWRIGHT_DATA_DIR=/data \
    MEALWRIGHT_FRONTEND_DIR=/app/frontend
USER mealwright
VOLUME /data
EXPOSE 8080
# Asks the app itself, on the container's own loopback address.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/api/v1/version', timeout=4).status == 200 else 1)"]
CMD ["python", "-m", "mealwright"]
