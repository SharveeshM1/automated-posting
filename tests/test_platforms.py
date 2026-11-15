"""Per-platform tests against httpx.MockTransport.

These verify that each integration builds the request we expect from the API docs
and parses the documented response shape. They do not call the real services.
"""
import asyncio
import json

import httpx
import pytest

from app.config import Settings
from app.platforms import PLATFORM_CLASSES, build_platforms
from app.platforms.base import PlatformError
from app.platforms.bluesky import BlueskyPlatform
from app.platforms.devto import DevToPlatform, make_title
from app.platforms.github_gist import GitHubGistPlatform
from app.platforms.mastodon import MastodonPlatform
from app.platforms.gitlab_snippet import GitLabSnippetPlatform

LINK = "https://example.com/x"
MESSAGE = f"Grow café traffic → {LINK}"


def settings(**values) -> Settings:
    return Settings(_env_file=None, **values)


def run(platform_cls, cfg, handler, verify=False, message=MESSAGE, link=LINK):
    """Publish through a mock transport; return (post, public, recorded_requests)."""
    calls = []

    def recording(request):
        calls.append(request)
        return handler(request)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(recording)) as client:
            platform = platform_cls(cfg, client)
            post = await platform.publish(message, link)
            public = await platform.verify_public(post) if verify else None
            return post, public

    post, public = asyncio.run(go())
    return post, public, calls


def test_five_platforms_are_registered():
    platforms = build_platforms(settings(), client=None)
    assert len(platforms) == 5
    assert [platform.name for platform in platforms] == [
        "Bluesky",
        "Mastodon",
        "DEV Community",
        "GitHub Gist",
        "GitLab Snippets",
    ]
    assert len({p.name for p in platforms}) == len(platforms)
    assert len(PLATFORM_CLASSES) == len(platforms)


def test_missing_config_reports_env_var_names():
    platform = GitLabSnippetPlatform(settings(), None)
    assert platform.missing_config() == ["GITLAB_TOKEN"]


def test_bluesky_creates_post_with_correct_link_facet():
    def handler(request):
        path = request.url.path
        if path.endswith("createSession"):
            return httpx.Response(200, json={"accessJwt": "jwt", "did": "did:plc:abc", "handle": "me.bsky.social"})
        if path.endswith("createRecord"):
            return httpx.Response(200, json={"uri": "at://did:plc:abc/app.bsky.feed.post/3kxyz", "cid": "c"})
        if path.endswith("getPosts"):
            return httpx.Response(200, json={"posts": [{"uri": "x"}]})
        return httpx.Response(404)

    cfg = settings(bluesky_handle="me.bsky.social", bluesky_app_password="pw")
    post, public, calls = run(BlueskyPlatform, cfg, handler, verify=True)

    assert post.url == "https://bsky.app/profile/me.bsky.social/post/3kxyz"
    assert public is True
    create = calls[1]
    assert create.headers["authorization"] == "Bearer jwt"
    body = json.loads(create.content)
    assert body["repo"] == "did:plc:abc" and body["collection"] == "app.bsky.feed.post"
    facet = body["record"]["facets"][0]
    raw = body["record"]["text"].encode("utf-8")
    assert raw[facet["index"]["byteStart"]:facet["index"]["byteEnd"]].decode() == LINK
    assert facet["features"][0]["uri"] == LINK


def test_bluesky_bad_credentials_surface_the_api_message():
    def handler(request):
        return httpx.Response(401, json={"error": "AuthenticationRequired", "message": "Invalid identifier or password"})

    with pytest.raises(PlatformError, match="Invalid identifier or password"):
        run(BlueskyPlatform, settings(bluesky_handle="a", bluesky_app_password="b"), handler)


def test_mastodon_posts_publicly_and_verifies_without_auth():
    def handler(request):
        if request.method == "POST":
            return httpx.Response(200, json={"id": "111", "url": "https://mastodon.social/@me/111", "visibility": "public"})
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"id": "111"})

    cfg = settings(mastodon_instance="mastodon.social/", mastodon_access_token="tok")
    post, public, calls = run(MastodonPlatform, cfg, handler, verify=True)

    assert post.url == "https://mastodon.social/@me/111"
    assert public is True
    assert str(calls[0].url) == "https://mastodon.social/api/v1/statuses"
    assert calls[0].headers["authorization"] == "Bearer tok"
    assert json.loads(calls[0].content) == {"status": MESSAGE, "visibility": "public"}


def test_mastodon_non_public_status_is_not_reported_public():
    def handler(request):
        return httpx.Response(200, json={"id": "1", "url": "https://m.example/1", "visibility": "unlisted"})

    post, public, _ = run(MastodonPlatform, settings(mastodon_instance="https://m.example", mastodon_access_token="t"), handler, verify=True)
    assert public is False


def test_devto_publishes_article_with_autolinked_cta():
    def handler(request):
        return httpx.Response(201, json={"id": 42, "url": "https://dev.to/me/grow-cafe-traffic-abc"})

    post, _, calls = run(DevToPlatform, settings(devto_api_key="key"), handler)
    assert post.url == "https://dev.to/me/grow-cafe-traffic-abc"
    assert calls[0].headers["api-key"] == "key"
    article = json.loads(calls[0].content)["article"]
    assert article["published"] is True
    assert f"<{LINK}>" in article["body_markdown"]
    assert LINK not in article["title"]


@pytest.mark.parametrize("platform_cls,cfg,create_response", [
    (DevToPlatform, {"devto_api_key": "key"}, {"id": 1, "url": "https://dev.to/me/post"}),
    (GitHubGistPlatform, {"github_token": "t"},
     {"id": "g1", "html_url": "https://gist.github.com/me/g1", "public": True}),
])
def test_blocked_post_page_with_http_200_is_not_public(platform_cls, cfg, create_response):
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, text="This post has been blocked by our spam filter.")
        status = 201 if platform_cls in (DevToPlatform, GitHubGistPlatform) else 200
        return httpx.Response(status, json=create_response)

    _, public, _ = run(platform_cls, settings(**cfg), handler, verify=True)
    assert public is False


def test_devto_title_handling():
    assert make_title(f"Hello world {LINK}", LINK) == "Hello world"
    assert make_title(LINK, LINK) == "Check this out"
    assert len(make_title("w " * 100 + LINK, LINK)) <= 80


def test_gitlab_snippet_posts_and_verifies_raw_file_without_token():
    token = "GITLAB-TEST-TOKEN"
    raw_url = "https://gitlab.com/-/snippets/123/raw"

    def handler(request):
        if request.method == "POST":
            assert str(request.url) == "https://gitlab.com/api/v4/snippets"
            assert request.headers["PRIVATE-TOKEN"] == token
            body = json.loads(request.content)
            assert body == {
                "title": make_title(MESSAGE, LINK),
                "visibility": "public",
                "files": [{"file_path": "message.md", "content": MESSAGE}],
            }
            return httpx.Response(201, json={
                "web_url": "https://gitlab.com/-/snippets/123",
                "visibility": "public",
                "files": [{"raw_url": raw_url}],
            })

        assert str(request.url) == raw_url
        assert "PRIVATE-TOKEN" not in request.headers
        return httpx.Response(200, text="Grow café traffic →")

    post, public, calls = run(
        GitLabSnippetPlatform,
        settings(gitlab_token=token),
        handler,
        verify=True,
    )
    assert post.url == "https://gitlab.com/-/snippets/123"
    assert post.external_id == raw_url
    assert public is True
    assert [call.method for call in calls] == ["POST", "GET"]


def test_gitlab_snippet_non_201_error_redacts_token():
    token = "GITLAB-TEST-TOKEN"

    def handler(request):
        return httpx.Response(400, json={"message": f"invalid token: {token}"})

    with pytest.raises(PlatformError) as exc:
        run(GitLabSnippetPlatform, settings(gitlab_token=token), handler)
    assert "invalid token" in str(exc.value)
    assert token not in str(exc.value)


@pytest.mark.parametrize("raw_text", ["Blocked by spam filter", ""])
def test_gitlab_snippet_blocked_or_empty_raw_file_is_not_public(raw_text):
    def handler(request):
        if request.method == "POST":
            return httpx.Response(201, json={
                "web_url": "https://gitlab.com/-/snippets/123",
                "visibility": "public",
                "files": [{"raw_url": "https://gitlab.com/-/snippets/123/raw"}],
            })
        return httpx.Response(200, text=raw_text)

    _, public, _ = run(
        GitLabSnippetPlatform,
        settings(gitlab_token="test-token"),
        handler,
        verify=True,
    )
    assert public is False


def test_github_gist_is_created_public():
    def handler(request):
        return httpx.Response(201, json={"id": "g1", "html_url": "https://gist.github.com/me/g1", "public": True})

    post, _, calls = run(GitHubGistPlatform, settings(github_token="ghp"), handler)
    assert post.url == "https://gist.github.com/me/g1"
    assert calls[0].headers["authorization"] == "Bearer ghp"
    body = json.loads(calls[0].content)
    assert body["public"] is True and body["files"]["message.md"]["content"] == MESSAGE


