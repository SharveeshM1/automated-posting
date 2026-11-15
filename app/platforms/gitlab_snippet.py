import httpx

from app.platforms.base import (
    Platform,
    PlatformError,
    PublishedPost,
    error_from_response,
    verification_text,
)
from app.platforms.devto import make_title

API_URL = "https://gitlab.com/api/v4/snippets"


class GitLabSnippetPlatform(Platform):
    name = "GitLab Snippets"
    required_settings = ("gitlab_token",)

    async def publish(self, message: str, link: str) -> PublishedPost:
        response = await self.client.post(
            API_URL,
            headers={"PRIVATE-TOKEN": self.settings.gitlab_token},
            json={
                "title": make_title(message, link),
                "visibility": "public",
                "files": [{"file_path": "message.md", "content": message}],
            },
        )
        if response.status_code != 201:
            error = error_from_response(response)
            token = self.settings.gitlab_token
            error_text = str(error)
            if token:
                error_text = error_text.replace(token, "[redacted]")
            raise PlatformError(error_text) from error

        data = response.json()
        raw_url = data["files"][0]["raw_url"]
        return PublishedPost(
            url=data["web_url"],
            public_hint=data.get("visibility") == "public",
            external_id=raw_url,
            verification_text=verification_text(message, link),
        )

    async def verify_public(self, post: PublishedPost) -> bool:
        if post.public_hint is False:
            return False
        try:
            response = await self.client.get(post.external_id)
        except httpx.HTTPError:
            return False
        return (
            response.status_code == 200
            and bool(response.text.strip())
            and bool(post.verification_text)
            and post.verification_text in response.text
        )
