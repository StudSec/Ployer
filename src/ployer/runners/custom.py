import logging
import subprocess

from ployer.challenge import Challenge
from ployer.runners._utils import get_docker_name, get_docker_port
from ployer.runners.base import ChallengeRunner


class CustomRunner(ChallengeRunner):
    def run(self, challenge: Challenge) -> bool:
        logging.info(f"Starting {challenge.name} as custom container...")

        try:
            cmd = [
                "/bin/bash",
                challenge.path + "/Source/run.sh",
                "--hostname",
                self.config.hostname,
            ]
            cmd += [elem for flag_name in challenge.flag for elem in ("--flag", flag_name)]
            if self.config.registry:
                cmd += ["--registry", self.config.registry]

            subprocess.run(
                cmd,
                cwd=challenge.path + "/Source/",
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError as e:
            logging.exception(f"Non-zero exit code {e.returncode} whilst starting {challenge.name}: {e.stderr}")
            return False
        return True

    def get_host_data(self, challenge: Challenge) -> dict | None:
        port = get_docker_port(get_docker_name(challenge.name))
        if port is None:
            return None
        return {"port": port}

    def stop(self, challenge: Challenge) -> bool:
        logging.info(f"Stopping {challenge.name} custom container...")

        try:
            subprocess.run(
                ["/bin/bash", challenge.path + "/Source/destroy.sh"],
                cwd=challenge.path + "/Source/",
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError as e:
            logging.exception(f"Non-zero exit code {e.returncode} whilst stopping {challenge.name}: {e.stderr}")
            return False
        return True
