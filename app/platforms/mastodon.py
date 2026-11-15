import uuid

from app.platforms.base import Platform, PublishedPost, error_from_response


class MastodonPlatform(Platform):
    name = "Mastodon"
    required_settings = ("mastodon_instance", "mastodon_access_token")

    @property
    def _instance(self) -> str:
        instance = self.settings.mastodon_instance.strip().rstrip("/")
        return instance if instance.startswith(("http://", "https://")) else f"https://{instance}"

    async def publish(self, message: str, link: str) -> PublishedPost:
        response = await self.client.post(
            f"{self._instance}/api/v1/statuses",
            headers={
                "Authorization": f"Bearer {self.settings.mastodon_access_token}",
                "Idempotency-Key": uuid.uuid4().hex,
            },
            json={"status": message, "visibility": "public"},
        )
        if response.status_code != 200:
            raise error_from_response(response)
        data = response.json()
        return PublishedPost(
            url=data.get("url") or f"{self._instance}/web/statuses/{data['id']}",
            public_hint=data.get("visibility") == "public",
            external_id=str(data["id"]),
        )

    async def verify_public(self, post: PublishedPost) -> bool:
        if post.public_hint is False:
            return False
        response = await self.client.get(f"{self._instance}/api/v1/statuses/{post.external_id}")
        return response.status_code == 200
