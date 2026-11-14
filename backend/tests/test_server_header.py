"""No `Server` header on any answer (0.9.5): not on pages, the API, static files or errors.

uvicorn adds `server: uvicorn` itself, below the app, so the app's own test client can't see
it. This starts the real server in its own process, like test_keep_alive.py.
"""

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

# Runs in a separate process: this one has the network guard on. Prints, for each path, its
# status and the names of its response headers, as JSON.
CLIENT = """
import http.client, json, sys, time
port = int(sys.argv[1])
out = {}
for path in sys.argv[2:]:
    for _ in range(100):
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            conn.request("GET", path)
            response = conn.getresponse()
            response.read()
            break
        except OSError:
            time.sleep(0.1)
    else:
        raise SystemExit("server never answered")
    out[path] = [response.status, sorted(name.lower() for name, _ in response.getheaders())]
    conn.close()
print(json.dumps(out))
"""

PATHS = {
    "/api/v1/version": 200,  # the API
    "/api/v1/health": 200,  # the health check
    "/api/v1/nope": 404,  # an error from the API
    "/": 200,  # an app page
    "/signed-out-page": 200,  # the app's page for any path (the web app draws it)
    "/asset.txt": 200,  # a static file
    "/_app/missing.js": 404,  # an error for a static file
}


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_no_answer_carries_a_server_header(tmp_path: Path) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<!doctype html><title>x</title>")
    (web / "asset.txt").write_text("a static file")
    port = free_port()
    env = {
        **os.environ,
        "MEALWRIGHT_DATA_DIR": str(tmp_path / "data"),
        "MEALWRIGHT_HOST": "127.0.0.1",
        "MEALWRIGHT_PORT": str(port),
        "MEALWRIGHT_RUN_JOBS": "false",
        "MEALWRIGHT_FRONTEND_DIR": str(web),
    }
    server = subprocess.Popen(
        [sys.executable, "-m", "mealwright"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        client = subprocess.run(  # noqa: S603 (fixed arguments)
            [sys.executable, "-I", "-c", CLIENT, str(port), *PATHS],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert client.returncode == 0, client.stdout + client.stderr
        answers = json.loads(client.stdout)
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
    for path, wanted_status in PATHS.items():
        status, names = answers[path]
        assert status == wanted_status, (path, status)
        assert "server" not in names, (path, names)
        assert "content-security-policy" in names, (path, names)  # it was our answer
