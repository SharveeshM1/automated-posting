from typing import List

import httpx

from app.config import Settings
from app.platforms.base import Platform
from app.platforms.bluesky import BlueskyPlatform
from app.platforms.devto import DevToPlatform
from app.platforms.github_gist import GitHubGistPlatform
from app.platforms.mastodon import MastodonPlatform
from app.platforms.gitlab_snippet import GitLabSnippetPlatform

PLATFORM_CLASSES = (
    BlueskyPlatform,
    MastodonPlatform,
    DevToPlatform,
    GitHubGistPlatform,
    GitLabSnippetPlatform,
)


def build_platforms(settings: Settings, client: httpx.AsyncClient) -> List[Platform]:
    """Platform selection is internal: the caller only ever sends a message."""
    return [cls(settings, client) for cls in PLATFORM_CLASSES]
