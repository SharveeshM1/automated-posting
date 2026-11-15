"""API-level tests: validation rules and per-platform failure isolation."""
import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app, get_service
from app.platforms.base import Platform, PlatformError, PublishedPost
from app.services.posting_service import PostingService

LINK = "https://example.com"
VALID = f"Check out our latest business platform and grow your online visibility. {LINK}"


class OkPlatform(Platform):
    name = "OkPlatform"

    async def publish(self, message, link):
        return PublishedPost(url="https://example.com/post/1", public_hint=True)

    async def verify_public(self, post):
        return True


class RejectingPlatform(Platform):
    name = "RejectingPlatform"

    async def publish(self, message, link):
        raise PlatformError("Authentication failed (HTTP 401): bad token")


class CrashingPlatform(Platform):
    name = "CrashingPlatform"

    async def publish(self, message, link):
        raise RuntimeError("boom")


class UnconfiguredPlatform(Platform):
    name = "UnconfiguredPlatform"
    required_settings = ("some_token",)

    async def publish(self, message, link):
        raise AssertionError("must not be called without credentials")


def make_client(platforms):
    service = PostingService(platforms)
    app.dependency_overrides[get_service] = lambda: service
    return TestClient(app)


@pytest.fixture
def client():
    empty = SimpleNamespace(some_token="")
    platforms = [
        OkPlatform(None, None),
        RejectingPlatform(None, None),
        CrashingPlatform(None, None),
        UnconfiguredPlatform(empty, None),
    ]
    with make_client(platforms) as c:
        yield c
    app.dependency_overrides.clear()


def test_one_failure_does_not_stop_the_others(client):
    response = client.post("/posting", json={"message": VALID})
    assert response.status_code == 200
    body = response.json()

    assert body["success"] is True
    assert [r["platform"] for r in body["results"]] == [
        "OkPlatform", "RejectingPlatform", "CrashingPlatform", "UnconfiguredPlatform",
    ]
    ok, rejected, crashed, unconfigured = body["results"]

    assert ok["status"] == "success"
    assert ok["posted_url"] == "https://example.com/post/1"
    assert ok["public_access"] is True
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", ok["date"])
    assert re.fullmatch(r"\d{2}:\d{2}:\d{2}", ok["time"])
    assert ok["error"] is None

    for failed in (rejected, crashed, unconfigured):
        assert failed["status"] == "failed"
        assert failed["posted_url"] is None
        assert failed["public_access"] is False
        assert failed["date"] is None and failed["time"] is None
    assert "Authentication failed" in rejected["error"]
    assert "RuntimeError" in crashed["error"]
    assert unconfigured["error"] == "Not configured: set SOME_TOKEN"


def test_success_is_false_when_every_platform_fails():
    with make_client([RejectingPlatform(None, None), CrashingPlatform(None, None)]) as c:
        response = c.post("/posting", json={"message": VALID})
    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["success"] is False


@pytest.mark.parametrize(
    "message, expected",
    [
        ("", "must not be empty"),
        ("   ", "must not be empty"),
        ("a" * 190 + f" {LINK}", "must not exceed 200 characters"),
        ("No link in this message at all", "found none"),
        ("Only a scheme-less domain: example.com", "found none"),
        ("Wrong scheme ftp://example.com/file", "found none"),
        (f"Two links {LINK} and https://example.org", "found 2"),
        (f"Same link twice {LINK} {LINK}", "found 2"),
        ("Missing scheme www.example.com", "must start with http"),
        ("Bad host https://localhost/path", "not a valid URL"),
        ("Bad host https://not_a_domain/path", "not a valid URL"),
        ("Bad TLD https://example.c", "not a valid URL"),
        ("Bad port https://example.com:99999/", "not a valid URL"),
        ("Bad ip https://999.1.1.1/", "not a valid URL"),
        ("Credentials https://user:pw@example.com/", "not a valid URL"),
    ],
)
def test_invalid_messages_are_rejected(client, message, expected):
    response = client.post("/posting", json={"message": message})
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["errors"][0]["field"] == "message"
    assert expected in body["errors"][0]["error"]


def test_missing_and_malformed_bodies_are_rejected(client):
    assert client.post("/posting", json={}).status_code == 422
    assert client.post("/posting", json={"message": 123}).status_code == 422
    assert client.post("/posting", content="not json", headers={"content-type": "application/json"}).status_code == 422


@pytest.mark.parametrize(
    "message",
    [
        "x" * (200 - len(LINK) - 1) + f" {LINK}",  # exactly 200 characters
        f"Visit {LINK}.",  # trailing sentence punctuation is not part of the link
        f"(see {LINK}/path?a=1&b=2#frag)",
        "Unicode café ☕ https://example.com/café",
        "IP address links work too http://192.168.1.10:8080/x",
    ],
)
def test_valid_messages_are_accepted(client, message):
    assert len(message) <= 200
    assert client.post("/posting", json={"message": message}).status_code == 200
