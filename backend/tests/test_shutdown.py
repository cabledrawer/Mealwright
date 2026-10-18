"""Stopping the real server while a live stream is open (sync protocol section 10).

uvicorn waits for open connections before it runs the app's own shutdown, and a live
stream never ends by itself, so the server must end the streams itself when asked to stop.
"""

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

# Signs up, opens the live stream, says so, and reports when the server ends the stream.
CLIENT = """
import http.client, json, sys, time
port = int(sys.argv[1])
origin = f"http://127.0.0.1:{port}"
body = json.dumps({"name": "Tess", "username": "tess", "password": "correct horse battery"})
setup = None
for _ in range(100):
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        headers = {"Origin": origin, "Content-Type": "application/json"}
        conn.request("POST", "/api/v1/setup", body, headers)
        setup = conn.getresponse()
        break
    except OSError:
        time.sleep(0.1)
assert setup is not None and setup.status == 201, setup
cookie = setup.getheader("set-cookie").split(";")[0]
setup.read()
stream = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
stream.request("GET", "/api/v1/events", headers={"Cookie": cookie, "Origin": origin})
response = stream.getresponse()
assert response.status == 200
seen = b""
while b"hello" not in seen:
    seen += response.fp.readline()
print("streaming", flush=True)
try:
    while response.fp.readline():
        pass
except OSError:
    pass
print("stream ended", flush=True)
"""


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.skipif(sys.platform == "win32", reason="needs POSIX signals")
def test_stops_promptly_while_a_live_stream_is_open(tmp_path: Path) -> None:
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
    # The client is a separate process: this one has the network guard on.
    client = subprocess.Popen(  # noqa: S603 (fixed arguments)
        [sys.executable, "-I", "-c", CLIENT, str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        assert client.stdout is not None
        assert client.stdout.readline().strip() == "streaming"
        started = time.monotonic()
        server.send_signal(signal.SIGTERM)
        server.wait(timeout=10)
        assert time.monotonic() - started < 4
        assert client.stdout.readline().strip() == "stream ended"
    finally:
        for process in (server, client):
            if process.poll() is None:
                process.kill()
                process.wait()
