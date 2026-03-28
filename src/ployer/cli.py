import argparse
import logging
import os
from pathlib import Path

import termcolor

from ployer.challenge import Challenge, load_challenge
from ployer.config import Config
from ployer.deployers.ctfd import upload_ctfd
from ployer.runners.base import ChallengeRunner
from ployer.runners.cm import ChallManagerRunner
from ployer.runners.custom import CustomRunner
from ployer.runners.docker import DockerRunner
from ployer.runners.swarm import SwarmRunner


class _ColorFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__()
        self._colors = {
            logging.DEBUG: "white",
            logging.INFO: "light_blue",
            logging.WARNING: "yellow",
            logging.ERROR: "red",
            logging.CRITICAL: "magenta",
        }

    def format(self, record: logging.LogRecord) -> str:
        color = self._colors.get(record.levelno, "grey")
        return f"{termcolor.colored(record.getMessage(), color)}"


def setup_logging(level: str) -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(level.upper())
    root_logger.handlers.clear()

    handler = logging.StreamHandler()
    handler.setFormatter(_ColorFormatter())
    root_logger.addHandler(handler)


def discover_challenges(challenges_root: Path) -> list[Challenge]:
    challenge_files = sorted(challenges_root.rglob("challenge.toml"))
    return [load_challenge(str(challenge_file)) for challenge_file in challenge_files]


def _matches(value: str, patterns: str) -> bool:
    if patterns == "*":
        return True
    filters = [item.strip() for item in patterns.split(",") if item.strip()]
    return any(item.lower() in value.lower() for item in filters)


def _pick_runner(runner_name: str, challenge: Challenge, config: Config) -> ChallengeRunner:
    if os.path.isfile(os.path.join(challenge.path, "Source", "run.sh")):
        return CustomRunner(config)
    if runner_name == "swarm":
        return SwarmRunner(config)
    if challenge.instanced:
        return ChallManagerRunner(config)
    return DockerRunner(config)


def _foreach_challenge(challenges: list[Challenge], pattern: str, action) -> None:
    for challenge in challenges:
        if _matches(challenge.name, pattern):
            action(challenge)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ployer CLI")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Path to challenges root")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Interface/hostname for challenge scripts")
    parser.add_argument("--registry", type=str, help="Docker registry for runner scripts")
    parser.add_argument(
        "--type", choices=["static", "dynamic"], default="static", help="Challenge type for CTFd upload"
    )
    parser.add_argument(
        "--runner",
        choices=["docker", "swarm"],
        help="Runner backend for challenges that do not have a custom or instancer setup",
    )
    parser.add_argument(
        "--ctfd", type=str, const="*", nargs="?", help="Upload challenge(s) to CTFd instance at given 'URL TOKEN'"
    )
    parser.add_argument("--log-level", default="INFO", help="Python logging level")

    parser.add_argument("--challenges", action="store_true", help="List information of challenges")
    parser.add_argument("--run", type=str, const="*", nargs="?", help="Run challenge(s)")
    parser.add_argument("--stop", type=str, const="*", nargs="?", help="Stop challenge(s)")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    config = Config(
        type=args.type,
        hostname=args.host,
        registry=args.registry,
        ctfd_url=args.ctfd.split()[0] if args.ctfd else None,
        ctfd_token=args.ctfd.split()[1] if args.ctfd else None,
    )
    setup_logging(args.log_level)

    if not any([args.challenges, args.run, args.stop, args.port]):
        parser.print_help()
        return 0

    challenges = discover_challenges(args.root)
    if not challenges:
        logging.warning(f"No challenges found under: {args.root}")
        return 1

    if args.challenges:
        _foreach_challenge(challenges, "*", lambda challenge: print(challenge))
    if args.run:
        # Stop challenges before running to make sure everything is updated
        _foreach_challenge(
            challenges, args.run, lambda challenge: _pick_runner(args.runner, challenge, config).stop(challenge)
        )
        _foreach_challenge(
            challenges, args.run, lambda challenge: _pick_runner(args.runner, challenge, config).run(challenge)
        )
    if args.stop:
        _foreach_challenge(
            challenges, args.stop, lambda challenge: _pick_runner(args.runner, challenge, config).stop(challenge)
        )
    if args.ctfd:
        _foreach_challenge(
            challenges,
            args.ctfd,
            lambda challenge: upload_ctfd(challenge, config, _pick_runner(args.runner, challenge, config)),
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
