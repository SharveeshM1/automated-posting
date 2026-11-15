from datetime import datetime, timezone

from app.platforms.base import Platform, PublishedPost, error_from_response

PUBLIC_API = "https://public.api.bsky.app"


def build_link_facets(text: str, link: str) -> list:
    """Bluesky needs explicit facets (UTF-8 byte offsets) for a link to be clickable."""
    start = text.find(link)
    if start < 0:
        return []
    byte_start = len(text[:start].encode("utf-8"))
    return [
        {
            "index": {"byteStart": byte_start, "byteEnd": byte_start + len(link.encode("utf-8"))},
            "features": [{"$type": "app.bsky.richtext.facet#link", "uri": link}],
        }
    ]


class BlueskyPlatform(Platform):
    name = "Bluesky"
    required_settings = ("bluesky_handle", "bluesky_app_password")

    async def publish(self, message: str, link: str) -> PublishedPost:
        base = self.settings.bluesky_service.rstrip("/")

        session = await self.client.post(
            f"{base}/xrpc/com.atproto.server.createSession",
            json={
                "identifier": self.settings.bluesky_handle,
                "password": self.settings.bluesky_app_password,
            },
        )
        if session.status_code != 200:
            raise error_from_response(session)
        session_data = session.json()

        record = {
            "$type": "app.bsky.feed.post",
            "text": message,
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "facets": build_link_facets(message, link),
        }
        created = await self.client.post(
            f"{base}/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {session_data['accessJwt']}"},
            json={"repo": session_data["did"], "collection": "app.bsky.feed.post", "record": record},
        )
        if created.status_code != 200:
            raise error_from_response(created)

        at_uri = created.json()["uri"]
        rkey = at_uri.rsplit("/", 1)[-1]
        return PublishedPost(
            url=f"https://bsky.app/profile/{session_data['handle']}/post/{rkey}",
            external_id=at_uri,
        )

    async def verify_public(self, post: PublishedPost) -> bool:
        # bsky.app is a single-page app that answers 200 for anything, so ask the
        # unauthenticated public API whether the post exists instead.
        response = await self.client.get(
            f"{PUBLIC_API}/xrpc/app.bsky.feed.getPosts", params={"uris": post.external_id}
        )
        return response.status_code == 200 and bool(response.json().get("posts"))
