import asyncio
import logging
from datetime import datetime, timezone
from typing import Sequence

import httpx

from app.links import find_links
from app.platforms.base import Platform, PlatformError, PublishedPost
from app.schemas import PlatformResult, PostingResponse

logger = logging.getLogger(__name__)

VERIFY_TIMEOUT_SECONDS = 10.0


class PostingService:
    def __init__(self, platforms: Sequence[Platform], timeout: float = 30.0):
        self.platforms = list(platforms)
        self.timeout = timeout

    async def post(self, message: str) -> PostingResponse:
        link = find_links(message)[0]  # message was already validated to hold exactly one
        # Every platform runs concurrently and in isolation: _post_one never raises.
        results = await asyncio.gather(*(self._post_one(p, message, link) for p in self.platforms))
        return PostingResponse(
            success=any(r.status == "success" for r in results), results=list(results)
        )

    async def _post_one(self, platform: Platform, message: str, link: str) -> PlatformResult:
        missing = platform.missing_config()
        if missing:
            return self._failed(platform, f"Not configured: set {', '.join(missing)}")

        try:
            post = await asyncio.wait_for(platform.publish(message, link), timeout=self.timeout)
        except PlatformError as exc:
            return self._failed(platform, str(exc))
        except (asyncio.TimeoutError, httpx.TimeoutException):
            return self._failed(platform, "Request timed out")
        except httpx.HTTPError as exc:
            return self._failed(platform, f"Network error ({type(exc).__name__})")
        except Exception as exc:  # a bug or an unexpected payload must not stop other platforms
            logger.exception("Unexpected error while posting to %s", platform.name)
            return self._failed(platform, f"Unexpected error ({type(exc).__name__})")

        public = await self._is_public(platform, post)
        now = datetime.now(timezone.utc)
        return PlatformResult(
            platform=platform.name,
            status="success",
            posted_url=post.url,
            public_access=public,
            date=now.date().isoformat(),
            time=now.strftime("%H:%M:%S"),
        )

    async def _is_public(self, platform: Platform, post: PublishedPost) -> bool:
        try:
            return await asyncio.wait_for(platform.verify_public(post), timeout=VERIFY_TIMEOUT_SECONDS)
        except Exception:
            logger.warning("Could not verify public access for %s", platform.name, exc_info=True)
            return False

    @staticmethod
    def _failed(platform: Platform, error: str) -> PlatformResult:
        logger.warning("%s failed: %s", platform.name, error)
        return PlatformResult(platform=platform.name, status="failed", error=error)
