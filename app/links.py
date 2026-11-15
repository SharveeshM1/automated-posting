"""Finding and validating the single CTA link inside a message."""
import re
from typing import List
from urllib.parse import urlparse

MAX_MESSAGE_LENGTH = 200

_CANDIDATE = re.compile(r"(?<!\w)(?:https?://|www\.)\S+", re.IGNORECASE)
_TRAILING_PUNCTUATION = ".,;:!?)]}'\""
_DOMAIN = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:[a-z]{2,63}|xn--[a-z0-9-]{1,59})$"
)
_IPV4 = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


def find_links(text: str) -> List[str]:
    """Return every link-looking token, minus trailing sentence punctuation."""
    return [m.group(0).rstrip(_TRAILING_PUNCTUATION) for m in _CANDIDATE.finditer(text)]


def is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        _ = parsed.port  # raises ValueError for a malformed port
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    if parsed.username or parsed.password:
        return False
    host = parsed.hostname
    if not host:
        return False
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return False
    if _IPV4.match(host):
        return all(int(part) <= 255 for part in host.split("."))
    return bool(_DOMAIN.match(host))


def validate_message(message: str) -> str:
    """Return the cleaned message or raise ValueError with a user-facing reason."""
    message = message.strip()
    if not message:
        raise ValueError("Message must not be empty.")
    if len(message) > MAX_MESSAGE_LENGTH:
        raise ValueError(
            f"Message must not exceed {MAX_MESSAGE_LENGTH} characters (received {len(message)})."
        )

    links = find_links(message)
    if len(links) != 1:
        found = "none" if not links else str(len(links))
        raise ValueError(
            f"Message must contain exactly one CTA link starting with http:// or https:// (found {found})."
        )

    link = links[0]
    if link.lower().startswith("www."):
        raise ValueError("The CTA link must start with http:// or https://.")
    if not is_valid_url(link):
        raise ValueError(f"The CTA link is not a valid URL: {link}")
    return message
