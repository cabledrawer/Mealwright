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
# It waits for the server to start until a deadline, not a fixed number of tries: on a busy
# machine start-up took longer than the 10 seconds it once allowed (T4, 22 Nov).
CLIENT = """
import http.client, json, re, sys, time
port = int(sys.argv[1])
origin = f"http://127.0.0.1:{port}"
deadline = time.monotonic() + float(sys.argv[3])
# The first-run setup code, read from the server's own output, as a person would (PR A2).
code = None
while time.monotonic() < deadline:
    with open(sys.argv[2]) as output:
        found = re.search(r"setup code: ([A-Z0-9-]{14})", output.read())
    if found:
        code = found.group(1)
        break
    time.sleep(0.1)
assert code is not None, "no setup code in the server's output"
admin = {"name": "Tess", "username": "tess", "password": "correct horse battery"}
body = json.dumps({**admin, "setup_code": code})
setup = None
while time.monotonic() < deadline:
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
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


# How long the server may take to start on a slow, busy machine. The stop itself must still
# take under 4 seconds.
START_UP_LIMIT = 120.0


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
    output = tmp_path / "output.txt"
    server = subprocess.Popen(
        [sys.executable, "-m", "mealwright"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=output.open("w"),
    )
    # The client is a separate process: this one has the network guard on.
    client = subprocess.Popen(  # noqa: S603 (fixed arguments)
        [sys.executable, "-I", "-c", CLIENT, str(port), str(output), str(START_UP_LIMIT)],
        stdout=subprocess.PIPE,
        stderr=(tmp_path / "client.txt").open("w"),
        text=True,
    )
    try:
        assert client.stdout is not None
        line = client.stdout.readline().strip()
        assert line == "streaming", (tmp_path / "client.txt").read_text()[-2000:]
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
