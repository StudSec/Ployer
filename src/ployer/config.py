from dataclasses import dataclass


@dataclass(slots=True)
class Config:
    """Settings passed from CLI into runners."""

    type: str = "static"
    hostname: str = "127.0.0.1"
    registry: str | None = None
    ctfd_url: str | None = None
    ctfd_token: str | None = None
