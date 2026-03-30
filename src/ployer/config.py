from dataclasses import dataclass
from urllib.parse import urlsplit


def normalize_registry(registry: str | None) -> str | None:
    """Normalize registry input to Docker reference prefix format.

    Examples:
    - "https://registry.example.com/" -> "registry.example.com/"
    - "registry.example.com" -> "registry.example.com/"
    """

    if registry is None:
        return None

    value = registry.strip()
    if not value:
        return None

    parsed = urlsplit(value)

    if parsed.scheme:
        value = f"{parsed.netloc}{parsed.path}"
    elif value.startswith("//"):
        value = value[2:]

    value = value.strip().strip("/")
    if not value:
        return None

    return value + "/"


@dataclass(slots=True)
class Config:
    """Settings passed from CLI into runners."""

    type: str = "static"
    hostname: str = "127.0.0.1"
    registry: str | None = None
    ctfd_url: str | None = None
    ctfd_token: str | None = None
