import logging
import subprocess

from ployer.challenge import Challenge
from ployer.runners._utils import get_docker_name, get_docker_port, get_source_hash
from ployer.runners.base import ChallengeRunner


class DockerRunner(ChallengeRunner):
    def is_running(self, challenge: Challenge) -> bool | None:
        chall_name = get_docker_name(challenge.name)
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", chall_name],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return False
        return result.stdout.strip().lower() == "true"

    def has_changed(self, challenge: Challenge) -> bool | None:
        chall_name = get_docker_name(challenge.name)
        source_hash = get_source_hash(challenge.path + "/Source/")

        result = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                '{{ index .Config.Labels "ployer.source_hash" }}',
                chall_name,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return True

        running_hash = result.stdout.strip()
        if not running_hash:
            return True
        return running_hash != source_hash

    def run(self, challenge: Challenge) -> bool:
        logging.info(f"Starting {challenge.name} as standard Docker container...")

        chall_name = get_docker_name(challenge.name)
        source_hash = get_source_hash(challenge.path + "/Source/")

        try:
            subprocess.run(
                ["docker", "buildx", "build", "--load", "-t", chall_name, "."],
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
                    "--label",
                    f"ployer.source_hash={source_hash}",
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
            subprocess.run(
                ["docker", "rm", "-f", get_docker_name(challenge.name)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError as e:
            logging.exception(f"Non-zero exit code {e.returncode} whilst stopping {challenge.name}: {e.stderr}")
            return False
        return True
