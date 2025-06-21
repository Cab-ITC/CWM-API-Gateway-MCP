import pytest
import api_gateway.server as server

class DummyDB:
    def __init__(self, endpoint=None):
        self.endpoint = endpoint
    def find_endpoint_by_path_method(self, path, method):
        return self.endpoint
    def format_endpoint_for_display(self, endpoint):
        return f"DETAILS for {endpoint['path']}"

@pytest.mark.asyncio
async def test_get_api_endpoint_details_found():
    dummy_endpoint = {"path": "/tickets", "method": "get"}
    original_db = server.api_db
    server.api_db = DummyDB(dummy_endpoint)
    try:
        result = await server.get_api_endpoint_details("/tickets", "GET")
    finally:
        server.api_db = original_db
    assert result == "DETAILS for /tickets"

@pytest.mark.asyncio
async def test_get_api_endpoint_details_not_found():
    original_db = server.api_db
    server.api_db = DummyDB(None)
    try:
        result = await server.get_api_endpoint_details("/unknown", "GET")
    finally:
        server.api_db = original_db
    assert result == "No API endpoint found for GET /unknown."

@pytest.mark.asyncio
async def test_execute_api_call_endpoint_not_found(monkeypatch):
    original_db = server.api_db
    server.api_db = DummyDB(None)
    async def dummy_request(*args, **kwargs):
        return {}
    monkeypatch.setattr(server, "make_api_request", dummy_request)
    monkeypatch.setattr(server, "check_fast_memory", lambda *a, **k: None)
    try:
        result = await server.execute_api_call("/bad", "GET")
    finally:
        server.api_db = original_db
    assert result == "Warning: No documented API endpoint found for GET /bad. Proceeding with caution."

@pytest.mark.asyncio
async def test_execute_api_call_success(monkeypatch):
    dummy_endpoint = {"path": "/tickets", "method": "get"}
    original_db = server.api_db
    server.api_db = DummyDB(dummy_endpoint)
    async def dummy_request(*args, **kwargs):
        return {"ok": True}
    monkeypatch.setattr(server, "make_api_request", dummy_request)
    monkeypatch.setattr(server, "check_fast_memory", lambda *a, **k: None)
    monkeypatch.setattr(server, "format_endpoint_for_saving", lambda *a, **k: "INFO")
    server.current_query_from_fast_memory = False
    try:
        result = await server.execute_api_call("/tickets", "GET")
    finally:
        server.api_db = original_db
    assert "\n  \"ok\": true\n" in result
    assert "=== SUCCESSFUL API CALL ===" in result
    assert "INFO" in result
