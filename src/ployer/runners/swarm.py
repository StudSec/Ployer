import json
import logging
import subprocess

from ployer.challenge import Challenge
from ployer.runners._utils import get_docker_name, get_source_hash
from ployer.runners.base import ChallengeRunner


class SwarmRunner(ChallengeRunner):
    def is_running(self, challenge: Challenge) -> bool | None:
        result = subprocess.run(
            ["docker", "service", "inspect", get_docker_name(challenge.name)],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    def has_changed(self, challenge: Challenge) -> bool | None:
        source_hash = get_source_hash(challenge.path + "/Source/")
        result = subprocess.run(
            [
                "docker",
                "service",
                "inspect",
                get_docker_name(challenge.name),
                "--format",
                '{{ index .Spec.Labels "ployer.source_hash" }}',
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
        logging.info(f"Starting {challenge.name} as swarm service...")

        chall_name = get_docker_name(challenge.name)
        chall_tag = self.config.registry + "swarm/" + chall_name
        source_hash = get_source_hash(challenge.path + "/Source/")

        try:
            subprocess.run(
                ["docker", "buildx", "build", "--push", "-t", chall_tag, "."],
                cwd=challenge.path + "/Source/",
                check=True,
            )

            # get the port from the built image
            port_result = subprocess.run(
                [
                    "docker",
                    "inspect",
                    chall_tag,
                    "--format",
                    "{{json .Config.ExposedPorts}}",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            ports_info = json.loads(port_result.stdout)
            if not ports_info:
                logging.error(f"No exposed ports found for {challenge.name}. Ensure the Dockerfile exposes a port.")
                return False
            port = next(iter(ports_info.keys())).split("/")[0]

            subprocess.run(
                [
                    "docker",
                    "service",
                    "create",
                    "--with-registry-auth",
                    "--name",
                    chall_name,
                    "--label",
                    f"ployer.source_hash={source_hash}",
                    "--replicas",
                    "1",
                    "--constraint",
                    "node.labels.type==challs",
                    "--publish",
                    f"target={port}",
                    chall_tag,
                ],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            logging.exception(f"Non-zero exit code {e.returncode} whilst starting {challenge.name}: {e.stderr}")
            return False
        return True

    def get_host_data(self, challenge: Challenge) -> dict | None:
        try:
            result = subprocess.run(
                [
                    "docker",
                    "service",
                    "inspect",
                    get_docker_name(challenge.name),
                    "--format",
                    "{{json .Endpoint.Ports}}",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            ports_info = json.loads(result.stdout)
            if ports_info:
                return {"port": ports_info[0]["PublishedPort"]}
        except subprocess.CalledProcessError as e:
            logging.exception(f"Non-zero exit code {e.returncode} whilst inspecting {challenge.name}: {e.stderr}")
        except (json.JSONDecodeError, KeyError):
            logging.exception(f"Error parsing port information for {challenge.name}")
        return None

    def stop(self, challenge: Challenge) -> bool:
        logging.info(f"Stopping {challenge.name} swarm service...")

        try:
            subprocess.run(
                ["docker", "service", "rm", get_docker_name(challenge.name)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError as e:
            logging.exception(f"Non-zero exit code {e.returncode} whilst stopping {challenge.name}: {e.stderr}")
            return False
        return True
