from app.platforms.base import Platform, PublishedPost, error_from_response, verification_text


class GitHubGistPlatform(Platform):
    name = "GitHub Gist"
    required_settings = ("github_token",)

    async def publish(self, message: str, link: str) -> PublishedPost:
        response = await self.client.post(
            "https://api.github.com/gists",
            headers={
                "Authorization": f"Bearer {self.settings.github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={
                "description": message,
                "public": True,
                "files": {"message.md": {"content": message}},
            },
        )
        if response.status_code != 201:
            raise error_from_response(response)
        data = response.json()
        return PublishedPost(
            url=data["html_url"], public_hint=data.get("public"), external_id=data.get("id"),
            verification_text=verification_text(message, link),
        )
