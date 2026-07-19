"""Offline tests for ImmichClient tag application (mocked HTTPX transport)."""

from __future__ import annotations

import json

import httpx

from immich_cli.client import ImmichClient


def _client_with_handler(handler: object) -> ImmichClient:
    """Build an ImmichClient whose HTTPX client uses a mock transport."""
    client = ImmichClient("https://example.com/api", "KEY", timeout=5)
    client._client = httpx.Client(
        base_url="https://example.com/api",
        headers={"X-API-Key": "KEY"},
        transport=httpx.MockTransport(handler),
    )
    return client


def test_apply_tags_uses_correct_endpoint_and_body():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/tags") and request.method == "GET":
            return httpx.Response(200, json=[{"id": "t1", "value": "Vacation"}])
        if url.endswith("/tags/assets") and request.method == "PUT":
            captured["method"] = request.method
            captured["url"] = url
            captured["json"] = json.loads(request.content)
            return httpx.Response(200, json={})
        return httpx.Response(200, json={})

    client = _client_with_handler(handler)
    client.apply_tags("asset-1", ["Vacation"])

    assert captured["method"] == "PUT"
    assert captured["url"].endswith("/tags/assets")
    assert captured["json"] == {"tagIds": ["t1"], "assetIds": ["asset-1"]}


def test_apply_tags_creates_missing_hierarchy():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/tags") and request.method == "GET":
            return httpx.Response(200, json=[])
        if url.endswith("/tags") and request.method == "POST":
            body = json.loads(request.content)
            tid = "id-" + body["name"]
            seen[body["name"]] = tid
            return httpx.Response(201, json={"id": tid})
        if url.endswith("/tags/assets") and request.method == "PUT":
            seen["bulk"] = json.loads(request.content)
            return httpx.Response(200, json={})
        return httpx.Response(200, json={})

    client = _client_with_handler(handler)
    client.apply_tags("asset-1", ["Parent/Child"])

    assert "Parent" in seen
    assert "Child" in seen
    # The leaf id (Child) is what gets linked to the asset.
    assert seen["bulk"]["tagIds"] == [seen["Child"]]
    assert seen["bulk"]["assetIds"] == ["asset-1"]
