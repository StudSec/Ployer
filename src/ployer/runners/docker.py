import logging
import subprocess

from ployer.challenge import Challenge
from ployer.runners._utils import get_docker_name, get_docker_port
from ployer.runners.base import ChallengeRunner


class DockerRunner(ChallengeRunner):
    def run(self, challenge: Challenge) -> bool:
        logging.info(f"Starting {challenge.name} as standard Docker container...")

        chall_name = get_docker_name(challenge.name)

        try:
            subprocess.run(
                ["docker", "build", "-t", chall_name, "."],
                cwd=challenge.path + "/Source/",
                check=True,
            )

            subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--rm",
                    "-P",
                    "--name",
                    chall_name,
                    "--cpus=0.5",
                    "--memory=256m",
                    chall_name,
                ],
                check=True,
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
        logging.info(f"Stopping {challenge.name} standard Docker container...")

        try:
            subprocess.run(["docker", "rm", "-f", get_docker_name(challenge.name)], check=True)
        except subprocess.CalledProcessError as e:
            logging.exception(f"Non-zero exit code {e.returncode} whilst stopping {challenge.name}: {e.stderr}")
            return False
        return True
