from abc import ABC, abstractmethod

from ployer.challenge import Challenge
from ployer.config import Config


class ChallengeRunner(ABC):
    """Abstract base class for all challenge deployment methods."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()

    def is_running(self, challenge: Challenge) -> bool | None:
        """Returns challenge runtime state.

        - ``True``: currently running
        - ``False``: not running
        - ``None``: unknown / unsupported check
        """
        return None

    def has_changed(self, challenge: Challenge) -> bool | None:
        """Returns whether a running challenge changed and needs rebuild.

        - ``True``: changed, should rebuild
        - ``False``: unchanged, can keep running
        - ``None``: unknown / unsupported check
        """
        return None

    @abstractmethod
    def run(self, challenge: Challenge) -> bool:
        """Starts the challenge. Returns True if successful."""
        pass

    @abstractmethod
    def get_host_data(self, challenge: Challenge) -> dict | None:
        """Returns relevant host data for the challenge if applicable."""
        pass

    @abstractmethod
    def stop(self, challenge: Challenge) -> bool:
        """Stops the challenge. Returns True if successful."""
        pass
