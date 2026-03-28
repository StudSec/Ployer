import json
import logging
import subprocess

from ployer.challenge import Challenge
from ployer.runners._utils import get_docker_name
from ployer.runners.base import ChallengeRunner


class ChallManagerRunner(ChallengeRunner):
    def run(self, challenge: Challenge) -> bool:
        logging.info(f"Starting {challenge.name} as chall manager container...")

        chall_name = get_docker_name(challenge.name)
        chall_tag = "swarm/" + chall_name

        try:
            subprocess.run(
                ["docker", "build", "-t", chall_tag, "."],
                cwd=challenge.path + "/Source/",
                check=True,
            )

            subprocess.run(
                ["docker", "push", chall_tag],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            logging.exception(f"Non-zero exit code {e.returncode} whilst starting {challenge.name}: {e.stderr}")
            return False
        # Users start the challenge themselves a la instancing
        return True

    def get_host_data(self, challenge: Challenge) -> dict | None:
        try:
            port = subprocess.run(
                ["docker", "inspect", get_docker_name(challenge.name), "--format", "{{json .Config.ExposedPorts}}"],
                capture_output=True,
                text=True,
                check=True,
            )
            port = next(json.loads(port.stdout).keys())[0].split("/")[0]
        except subprocess.CalledProcessError as e:
            logging.exception(f"Non-zero exit code {e.returncode} whilst inspecting {challenge.name}: {e.stderr}")
            return None
        return {
            "timeout": 1800,
            "shared": "false",
            "mana_cost": 1,
            "destroy_on_flag": "true",
            "scenario": f"{self.config.registry}chall-manager/deploy:latest",
            "additional": {
                "port": port,
                "docker_host": "ssh://challs",
                "hostname": self.config.hostname,
                "image": "swarm/" + get_docker_name(challenge.name),
                "protocol_url": "http" if challenge.url and "http" in challenge.url else "tcp",
            },
        }

    def stop(self, challenge: Challenge) -> bool:
        logging.info(f"Stopping {challenge.name} chall manager container...")
        # Users stop the challenge themselves a la instancing
        return True
