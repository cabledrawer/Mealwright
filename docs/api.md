# The API

Everything the Mealwright web app does, it does through the same public API, so scripts and other apps can do it too. This page says how to get in. It doesn't list every call: the OpenAPI description does.

## Where it is

- **Base address:** `https://<your Mealwright address>/api/v1`, for example `https://mealwright.example.com/api/v1`.
- **The OpenAPI description:** `https://<your Mealwright address>/api/v1/openapi.json`. It lists every call, what it takes and what it gives back, and it needs no sign-in. Mealwright serves no web page for browsing it, because the usual pages load scripts from a third-party site, which Mealwright never does. Open the JSON in any OpenAPI viewer on your own computer, or in a tool you trust.
- **The version:** `GET /api/v1/version` answers `{"version": "…"}` with no sign-in. Update tools such as Diun and Renovate can use it. **Pre-releases use Python's spelling:** a test version such as `0.9.5-beta.2` answers `0.9.5b2` (the CHANGELOG, the tag, the image and the About screen say `0.9.5-beta.2`). A tool that compares the answer with image tags has to treat the two spellings as the same version; final releases (`0.9.5`, `1.0.0`) have only the plain form, so nothing differs for them.
- **The health check:** `GET /api/v1/health` answers `{"status": "ok"}` with no sign-in when the database answers a trivial query, and 503 `{"status": "unavailable"}` (with the `detail` and `code` every error has, the same whatever went wrong) when it does not. It says nothing else (no version, no counts, no reason). The image's health check calls it.

## Make an API token

Only an admin can make one.

1. Open Settings › API tokens.
2. Under **New token**, give it a **Name** that says what it is for (for example "Shopping widget").
3. Choose what it **Can** do: **Read only** or **Read and change**.
4. Choose when it **Expires**: Never, 30 days, 1 year, or Pick a date.
5. Press **Make token**. **The token is shown once.** Copy it now: Mealwright keeps only a fingerprint of it, so it can't show it again. If you lose it, delete it and make another.

A read-only token starts `mw_ro_`. A read-and-change token starts `mw_rw_`. That makes one pasted somewhere it shouldn't be easy to spot. Treat it like a password.

## Use it

Send it in an `Authorization` header, to `/api/v1` only:

```bash
curl -H "Authorization: Bearer mw_ro_PLACEHOLDER" \
  "https://mealwright.example.com/api/v1/recipes?limit=5"
```

`mw_ro_PLACEHOLDER` stands for your own token. This asks for the first five recipes, A to Z.

Don't send a sign-in cookie at the same time: a request with both is refused.

## What a token can and can't do

- It acts as the admin who made it, **only while that person is still an admin** of the household. If they are made a Member or deleted, their tokens stop at once and for good. This is true even if they are taken out at your sign-in server only: do it in Settings › People too ([sso.md](sso.md)).
- A read-only token can't change anything.
- No token can manage people, change Outside connections, change sign-in settings (including making tokens) or use Backups & your data (backups, export, Delete everything). Do those in the web app.
- A token that doesn't work (unknown, deleted, ended, or the wrong shape) always gets the same answer, `401`, so nobody can tell which.
- Using a token writes nothing to Mealwright's log.
- To stop a token, delete it on the same screen.
