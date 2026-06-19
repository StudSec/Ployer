import logging
import subprocess

from ployer.challenge import Challenge
from ployer.runners.base import ChallengeRunner


class CustomRunner(ChallengeRunner):
    def is_running(self, challenge: Challenge) -> bool | None:
        return True

    def run(self, challenge: Challenge) -> bool:
        logging.info(f"Starting {challenge.name} as custom container...")

        try:
            cmd = [
                "/bin/bash",
                "./run.sh",
                "--hostname",
                self.config.hostname,
            ]
            cmd += [elem for flag_name in challenge.flag for elem in ("--flag", flag_name)]
            if self.config.registry:
                cmd += ["--registry", self.config.registry]

            result = subprocess.run(
                cmd,
                cwd=challenge.path + "/Source/",
                check=True,
                capture_output=True,
                text=True,
            )
            if result.stdout:
                logging.debug(result.stdout.strip())
        except subprocess.CalledProcessError as e:
            logging.exception(f"Non-zero exit code {e.returncode} whilst starting {challenge.name}: {e.stderr}")
            return False
        return True

    def get_host_data(self, challenge: Challenge) -> dict | None:
        port = subprocess.run(
            ["./get_port.sh"],
            cwd=challenge.path + "/Source/",
            capture_output=True,
            text=True,
            check=False,
        )
        if port.returncode != 0:
            return None
        return {"port": port.stdout.strip()}

    def stop(self, challenge: Challenge) -> bool:
        logging.info(f"Stopping {challenge.name} custom container...")

        try:
            result = subprocess.run(
                ["/bin/bash", "./destroy.sh"],
                cwd=challenge.path + "/Source/",
                check=True,
                capture_output=True,
                text=True,
            )
            if result.stdout:
                logging.debug(result.stdout.strip())
        except subprocess.CalledProcessError as e:
            logging.exception(f"Non-zero exit code {e.returncode} whilst stopping {challenge.name}: {e.stderr}")
            return False
        return True
