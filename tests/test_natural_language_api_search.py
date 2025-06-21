import pytest
from types import SimpleNamespace

import api_gateway.server as server

class DummyDB:
    def __init__(self, results):
        self._results = results
    def search_by_natural_language(self, query, limit):
        return self._results

@pytest.mark.asyncio
async def test_natural_language_api_search_formats_results():
    dummy_results = [
        {"method": "get", "path": "/tickets", "description": "List tickets", "category": "Service"},
        {"method": "post", "path": "/tickets", "description": "Create ticket", "category": "Service"},
    ]
    original_db = server.api_db
    server.api_db = DummyDB(dummy_results)
    try:
        response = await server.natural_language_api_search("tickets")
    finally:
        server.api_db = original_db
    assert "1. GET /tickets" in response
    assert "Category: Service" in response
    assert "Description: List tickets" in response
    assert "2. POST /tickets" in response

@pytest.mark.asyncio
async def test_natural_language_api_search_no_results():
    original_db = server.api_db
    server.api_db = DummyDB([])
    try:
        response = await server.natural_language_api_search("unknown")
    finally:
        server.api_db = original_db
    assert response == "No API endpoints found matching your query."
