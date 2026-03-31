import hashlib
import logging
import re
import subprocess
from pathlib import Path


def get_docker_name(challenge_name: str) -> str:
    return re.sub(r"[-. ]", "_", challenge_name.lower())


def get_source_hash(source_path: str) -> str:
    root = Path(source_path)
    hasher = hashlib.sha256()

    if not root.exists():
        return ""

    for item in sorted(root.rglob("*")):
        if item.is_file():
            rel = item.relative_to(root).as_posix()
            hasher.update(rel.encode("utf-8"))
            hasher.update(b"\0")
            hasher.update(item.read_bytes())
            hasher.update(b"\0")

    return hasher.hexdigest()


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
