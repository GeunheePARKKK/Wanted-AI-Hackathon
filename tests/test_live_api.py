"""Real HTTP smoke test, separate from the in-process API tests."""
import json
import socket
import threading
import time
from urllib.request import Request, urlopen

import uvicorn

from backend import main


def test_live_http_autofix(client):
    original = main.DATA_FILE.read_bytes()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        address = f"http://127.0.0.1:{listener.getsockname()[1]}"
        server = uvicorn.Server(uvicorn.Config(main.app, log_level="error"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert server.started, "HTTP server did not start"

            def request(path, method="GET"):
                with urlopen(Request(address + path, method=method), timeout=30) as response:
                    assert response.status == 200
                    return json.load(response)

            with urlopen(address, timeout=10) as response:
                assert response.status == 200
                assert b"<!doctype html>" in response.read().lower()
            before = request("/api/inspect")
            english = request("/api/inspect?lang=en")
            assert before["summary"] == english["summary"]
            assert before["summary"]["violations"] > 0
            assert before["violations"][0]["detail"] != english["violations"][0]["detail"]
            target = before["violations"][0]["id"]
            assert request(f"/api/resolve/{target}?lang=en")["candidates"]
            started = time.perf_counter()
            fixed = request("/api/autofix", "POST")
            elapsed = time.perf_counter() - started
            assert fixed["inspection"]["violations"] == []
            assert fixed["inspection"]["summary"]["score"] == 100
            assert request("/api/inspect") == fixed["inspection"]
            assert request("/api/report?lang=en")["summary"]["score"] == 100
            assert request("/api/undo", "POST") == before
            assert request("/api/redo", "POST") == fixed["inspection"]
            assert request("/api/storage") == {"saved_exists": False}
            assert request("/api/save", "POST") == {"saved": True}
            saved = main.SAVED_FILE.read_bytes()
            assert request("/api/storage") == {"saved_exists": True}
            assert request("/api/reset", "POST") == before
            assert request("/api/restore", "POST") == fixed["inspection"]
            assert main.SAVED_FILE.read_bytes() == saved
            assert main.DATA_FILE.read_bytes() == original
            print(f"\nHTTP autofix: {before['summary']['violations']} -> 0; score 100; {elapsed:.3f}s")
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive(), "HTTP server did not stop"
