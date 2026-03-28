from abc import ABC, abstractmethod

from ployer.challenge import Challenge
from ployer.config import Config


class ChallengeRunner(ABC):
    """Abstract base class for all challenge deployment methods."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()

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
