from app.platforms.base import Platform, PublishedPost, error_from_response, verification_text

API_URL = "https://dev.to/api/articles"


def make_title(message: str, link: str) -> str:
    text = " ".join(message.replace(link, "").split()).strip(" -–—:|")
    if not text:
        return "Check this out"
    return text if len(text) <= 80 else text[:77].rstrip() + "..."


class DevToPlatform(Platform):
    name = "DEV Community"
    required_settings = ("devto_api_key",)

    async def publish(self, message: str, link: str) -> PublishedPost:
        response = await self.client.post(
            API_URL,
            headers={
                "api-key": self.settings.devto_api_key,
                "Accept": "application/vnd.forem.api-v1+json",
            },
            json={
                "article": {
                    "title": make_title(message, link),
                    # <url> is a CommonMark autolink, so the CTA is always clickable.
                    "body_markdown": message.replace(link, f"<{link}>"),
                    "published": True,
                }
            },
        )
        if response.status_code not in (200, 201):
            raise error_from_response(response)
        data = response.json()
        return PublishedPost(
            url=data["url"], external_id=str(data.get("id", "")),
            verification_text=verification_text(message, link),
        )
