import os
import sys
import time
import socket
import subprocess
import httpx

# Helper functions

def _get_free_port():
    with socket.socket() as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]

def _wait_for_port(port, timeout=5):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("Server did not start")


def _start_server(port):
    env = os.environ.copy()
    env.update(
        {
            "FASTMCP_TRANSPORT": "streamable-http",
            "FASTMCP_PORT": str(port),
            "FASTMCP_HOST": "127.0.0.1",
            # Dummy ConnectWise env vars so server initializes cleanly
            "CONNECTWISE_API_URL": "https://example.com",
            "CONNECTWISE_COMPANY_ID": "dummy",
            "CONNECTWISE_PUBLIC_KEY": "dummy",
            "CONNECTWISE_PRIVATE_KEY": "dummy",
        }
    )
    proc = subprocess.Popen([sys.executable, "api_gateway_server.py"], env=env)
    _wait_for_port(port)
    return proc


def test_streamable_http_returns_session_and_202():
    port = _get_free_port()
    proc = _start_server(port)
    try:
        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        }
        headers = {
            "Accept": "application/json,text/event-stream",
            "Content-Type": "application/json",
        }
        resp = httpx.post(f"http://127.0.0.1:{port}/mcp/", json=init_payload, headers=headers)
        session_id = resp.headers.get("mcp-session-id")
        assert session_id is not None

        notif_payload = {"jsonrpc": "2.0", "method": "initialized"}
        headers["mcp-session-id"] = session_id
        resp2 = httpx.post(f"http://127.0.0.1:{port}/mcp/", json=notif_payload, headers=headers)
        assert resp2.status_code == 202
        assert resp2.headers.get("mcp-session-id") == session_id
    finally:
        proc.terminate()
        proc.wait()


def test_streamable_http_accept_header_validation():
    port = _get_free_port()
    proc = _start_server(port)
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        }
        bad_headers = {"Content-Type": "application/json"}
        resp = httpx.post(f"http://127.0.0.1:{port}/mcp/", json=payload, headers=bad_headers)
        assert resp.status_code == 406

        bad_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        resp = httpx.post(f"http://127.0.0.1:{port}/mcp/", json=payload, headers=bad_headers)
        assert resp.status_code == 406
    finally:
        proc.terminate()
        proc.wait()

