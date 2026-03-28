import os
import tomllib
from dataclasses import asdict, dataclass, field

import termcolor


@dataclass
class Challenge:
    uuid: str
    name: str
    flag: dict[str, int]
    difficulty: str
    description: str
    category: str
    path: str

    # Optionals
    url: str | None = None
    instanced: bool = False
    hidden: bool = False
    dynamic_flag: bool = False

    hints: dict[str, int] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    handouts: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        values = {
            key: value
            for key, value in asdict(self).items()
            if value not in [None, [], {}] and key not in ["uuid", "name"]
        }

        return "\n".join([
            termcolor.colored(f"{self.uuid} - {self.name}", "cyan"),
            *[f"\t{termcolor.colored(key, 'light_blue')}: {value}" for key, value in values.items()],
            "",
        ])


def load_challenge(filepath: str) -> Challenge:
    with open(filepath, "rb") as f:
        data = tomllib.load(f)

    challenge_uuid = next(iter(data.keys()))
    challenge_data = data[challenge_uuid]
    challenge_data["uuid"] = challenge_uuid
    challenge_data["category"] = filepath.rsplit("/", 2)[-2]
    challenge_data["path"] = filepath.rsplit("/", 1)[0]
    challenge_data["handouts"] = []

    for dirpath, _, filenames in os.walk(challenge_data["path"] + "/Handout"):
        for filename in filenames:
            challenge_data["handouts"].append(os.path.join(dirpath, filename))

    return Challenge(**challenge_data)
