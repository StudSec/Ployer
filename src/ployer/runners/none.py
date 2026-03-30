from ployer.challenge import Challenge
from ployer.config import Config
from ployer.runners.base import ChallengeRunner


class NoneRunner(ChallengeRunner):
    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()

    def run(self, challenge: Challenge) -> bool:
        return True

    def get_host_data(self, challenge: Challenge) -> dict | None:
        return None

    def stop(self, challenge: Challenge) -> bool:
        return True
