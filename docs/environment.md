# Environment variables

Mealwright reads these when it starts. Set them under `environment:` in `compose.yaml`. Most installs set only `MEALWRIGHT_TRUSTED_PROXIES`.

The Mealwright ones are read in `backend/src/mealwright/config.py`: each setting `foo_bar` is the variable `MEALWRIGHT_FOO_BAR`. Nothing else in the backend reads the environment, apart from `WEB_CONCURRENCY` below. Mealwright reads no `.env` file.

## Settings you may want to change

| Variable | Default | What it does |
| --- | --- | --- |
| `MEALWRIGHT_TRUSTED_PROXIES` | empty | The addresses or networks of your reverse proxy, comma-separated (for example `172.28.10.0/24`). Mealwright believes the `X-Forwarded-For`, `X-Forwarded-Proto` and `X-Forwarded-Host` headers only from these. Empty: it believes nobody's, so everyone looks like the proxy. `*` believes anyone: only safe if your proxy replaces those headers. See [install.md](install.md). |
| `MEALWRIGHT_ALLOW_PLAIN_HTTP` | `false` | `true` lets people sign in over plain `http://`. The password and cookie then travel unprotected, and Mealwright logs a warning at start. For trying it out on a network you trust only. |

## Settings the Docker image already sets

You rarely need to change these.

| Variable | Default | What it does |
| --- | --- | --- |
| `MEALWRIGHT_DATA_DIR` | `/data` in the code and in the image | Where Mealwright keeps everything: database, photos, backups, logs, `secret.key`. Mount your folder here. |
| `MEALWRIGHT_FRONTEND_DIR` | `/app/frontend` in the code; the image sets `/app/frontend` too | Where the built web app is. If the folder is missing, only the API is served. |

## Settings for special cases and tests

| Variable | Default | What it does |
| --- | --- | --- |
| `MEALWRIGHT_DATABASE_URL` | empty, meaning `sqlite:///<data folder>/mealwright.db` | The database address. It must be a SQLite address (`sqlite:///…`): any other database makes Mealwright refuse to start. Leave it unset. |
| `MEALWRIGHT_MIGRATE_ON_START` | `true` | Update the database when Mealwright starts, with a safety copy first ([upgrade.md](upgrade.md)). Switching it off is not needed for normal use. |
| `MEALWRIGHT_HOST` | `0.0.0.0` | The address the server listens on. In the container this is all addresses: only your reverse proxy should reach it. |
| `MEALWRIGHT_PORT` | `8080` | The port it listens on. The image exposes 8080 and its health check asks 8080, so leave it. |
| `MEALWRIGHT_RUN_JOBS` | `true` | Run the background jobs (thinning old history, deleting removed ingredients and recipes for good, backups, the daily update check, single sign-on session checks, tidying the log folder). It is off only in tests. |
| `MEALWRIGHT_EVENTS_KEEPALIVE_SECONDS` | `25` | How often the live-updates stream sends a keep-alive line. Only tests change it. |

## One variable Mealwright refuses

| Variable | What happens |
| --- | --- |
| `WEB_CONCURRENCY` | Mealwright runs as one worker only. If this is set to anything but empty or `1`, it won't start and says so. |

## Set in the Docker image, not by you

The Dockerfile also sets `PATH` (so the app's own Python is found), `PYTHONDONTWRITEBYTECODE=1` and `PYTHONUNBUFFERED=1` (log lines appear at once). The image does not need changing for these.

## What isn't here

There are no variables for telemetry, because there is none, and none for the outside connections: those are switches in Settings → Privacy, off by default ([README](../README.md#privacy)).
