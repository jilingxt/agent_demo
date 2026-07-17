import json
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from plugins.reasoning_visualizer.server import create_server


SNAPSHOT = {
    "schema_version": "1.0",
    "meta": {},
    "evidence": {"nodes": [], "edges": [], "counts": {}},
    "bayesian": {"runs": [], "count": 0},
}


def test_server_serves_health_snapshot_and_static_assets():
    server = create_server(SNAPSHOT, port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    base = f"http://{host}:{port}"
    try:
        with urlopen(f"{base}/api/health") as response:
            assert json.loads(response.read())["status"] == "ok"
        with urlopen(f"{base}/api/snapshot") as response:
            assert json.loads(response.read()) == SNAPSHOT
        with urlopen(f"{base}/") as response:
            assert b"reasoning_visualizer" not in response.read()
        with urlopen(f"{base}/app.js") as response:
            assert response.headers["Content-Type"].startswith("text/javascript") or response.headers["Content-Type"].startswith("application/javascript")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_server_is_read_only_and_localhost_only():
    with pytest.raises(ValueError):
        create_server(SNAPSHOT, host="0.0.0.0", port=0)

    server = create_server(SNAPSHOT, port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        request = Request(f"http://{host}:{port}/api/snapshot", data=b"{}", method="POST")
        with pytest.raises(HTTPError) as error:
            urlopen(request)
        assert error.value.code == 405
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
