import logging
import re
import subprocess


def get_docker_name(challenge_name: str) -> str:
    return re.sub(r"[-. ]", "_", challenge_name.lower())


def get_docker_port(challenge_name: str) -> int | None:
    try:
        result = subprocess.run(
            ["docker", "port", challenge_name],
            capture_output=True,
            text=True,
            check=True,
        )
        port_mapping = result.stdout.strip()
        if port_mapping:
            return int(port_mapping.split(":")[-1])
    except subprocess.CalledProcessError as e:
        logging.exception(f"Non-zero exit code {e.returncode} whilst getting port for {challenge_name}: {e.stderr}")
    return None
