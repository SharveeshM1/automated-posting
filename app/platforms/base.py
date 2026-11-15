import logging
import html
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

_ERROR_KEYS = ("error", "message", "description", "error_description", "error_msg")


class PlatformError(Exception):
    """A platform rejected the request. The message is safe to return to the caller."""


@dataclass(frozen=True)
class PublishedPost:
    url: str
    public_hint: Optional[bool] = None  # what the API itself said about visibility, if anything
    external_id: Optional[str] = None
    verification_text: Optional[str] = None


def error_from_response(response: httpx.Response) -> PlatformError:
    """Build a PlatformError from an API error response.

    Deliberately avoids httpx's raise_for_status(): its message contains the request
    URL, since some platforms include credentials in request URLs.
    """
    parts: List[str] = []
    try:
        data = response.json()
    except ValueError:
        data = None
    if isinstance(data, dict):
        parts = [str(data[k]) for k in _ERROR_KEYS if isinstance(data.get(k), str) and data[k]]
    detail = " - ".join(parts) if parts else (response.text or "").strip()[:200] or "no details"
    prefix = "Authentication failed" if response.status_code in (401, 403) else "Request rejected"
    return PlatformError(f"{prefix} (HTTP {response.status_code}): {detail}")


class Platform(ABC):
    name: str = ""
    # Names of Settings attributes that must be non-empty for this platform to run.
    required_settings: tuple = ()

    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings = settings
        self.client = client

    def missing_config(self) -> List[str]:
        return [
            attr.upper() for attr in self.required_settings if not getattr(self.settings, attr, "")
        ]

    @abstractmethod
    async def publish(self, message: str, link: str) -> PublishedPost:
        """Publish the message and return where it lives. Raise PlatformError on rejection."""

    async def verify_public(self, post: PublishedPost) -> bool:
        """Check, without credentials, that the post can be opened by anyone."""
        if post.public_hint is False:
            return False
        try:
            response = await self.client.get(post.url)
        except httpx.HTTPError:
            return False
        if response.status_code != 200:
            return False
        if post.verification_text is None:
            return True
        return post.verification_text in html.unescape(response.text)


def verification_text(message: str, link: str) -> str:
    """Return the first 25 characters of the message without its CTA URL."""
    return " ".join(message.replace(link, "").split())[:25]
