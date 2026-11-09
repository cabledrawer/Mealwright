"""An idle connection stays open long enough to be reused (F130, cabledrawer 9 Nov).

A reverse proxy (Caddy keeps idle connections to the app for 2 min) and the browser
tests' API client both send the next request on a connection that has been idle for a
while. With uvicorn's default of 5 s the server had already closed it, so the request
failed with "socket hang up". The server must keep idle connections open for longer than
a proxy does.
"""

import os
import socket
import subprocess
import sys
from pathlib import Path

from mealwright.__main__ import KEEP_ALIVE_SECONDS

# Asks for the version, waits longer than uvicorn's old 5 s with the connection idle, then
# asks again on the same connection. Prints "reused" or what went wrong.
CLIENT = """
import http.client, sys, time
port = int(sys.argv[1])
conn = None
for _ in range(100):
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request("GET", "/api/v1/version")
        first = conn.getresponse()
        break
    except OSError:
        conn = None
        time.sleep(0.1)
assert conn is not None
assert first.status == 200, first.status
first.read()
sock = conn.sock
time.sleep(float(sys.argv[2]))
try:
    conn.request("GET", "/api/v1/version")
    again = conn.getresponse()
    again.read()
except (OSError, http.client.HTTPException) as error:
    print(f"failed: {type(error).__name__}", flush=True)
else:
    same = conn.sock is sock
    print("reused" if again.status == 200 and same else f"other: {again.status} {same}", flush=True)
"""

# Caddy's reverse proxy keeps idle upstream connections for 2 minutes by default.
CADDY_IDLE_SECONDS = 120


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_keeps_idle_connections_longer_than_a_reverse_proxy() -> None:
    assert KEEP_ALIVE_SECONDS > CADDY_IDLE_SECONDS


def test_an_idle_connection_is_reused_after_more_than_five_seconds(tmp_path: Path) -> None:
    port = free_port()
    env = {
        **os.environ,
        "MEALWRIGHT_DATA_DIR": str(tmp_path / "data"),
        "MEALWRIGHT_HOST": "127.0.0.1",
        "MEALWRIGHT_PORT": str(port),
        "MEALWRIGHT_RUN_JOBS": "false",
        "MEALWRIGHT_FRONTEND_DIR": str(tmp_path / "none"),
    }
    server = subprocess.Popen(
        [sys.executable, "-m", "mealwright"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        # The client is a separate process: this one has the network guard on.
        client = subprocess.run(  # noqa: S603 (fixed arguments)
            [sys.executable, "-I", "-c", CLIENT, str(port), "6.5"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert client.stdout.strip() == "reused", client.stdout + client.stderr
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
