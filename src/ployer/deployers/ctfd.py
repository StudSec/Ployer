import logging
import os
import subprocess

import requests

from ployer.challenge import Challenge
from ployer.config import Config
from ployer.runners.base import ChallengeRunner


def challenge_to_ctfd(challenge: Challenge, config: Config, runner: ChallengeRunner) -> dict:
    data = {
        "name": challenge.name,
        "description": challenge.description,
        "category": challenge.category,
        "state": "visible" if not challenge.hidden else "hidden",
    }

    if challenge.instanced:
        host_data = runner.get_host_data(challenge)
        if host_data:
            data |= host_data
    else:
        host_data = runner.get_host_data(challenge)
        if host_data and challenge.url:
            port = host_data["port"]
            data["connection_info"] = challenge.url.replace("{{PORT}}", str(port)).replace("{{HOST}}", config.hostname)
    if config.type == "static":
        if challenge.instanced:
            # bit of a hack since chall manager doesnt really have static score
            return data | {
                "type": "dynamic_iac",
                "initial": next(iter(challenge.flag.values())),
                "decay": 20,
                "minimum": next(iter(challenge.flag.values())),
                "function": "logarithmic",
            }
        return {
            "value": next(iter(challenge.flag.values())),
        } | data

    return data | {
        "type": "dynamic_iac" if challenge.instanced else "dynamic",
        "initial": 500,
        "decay": 20,
        "minimum": 50,
        "function": "logarithmic",
    }


def upload_ctfd(challenge: Challenge, config: Config, runner: ChallengeRunner) -> None:  # noqa: C901
    if not config.ctfd_url or not config.ctfd_token:
        print("here")
        logging.error("CTFd URL and API key must be provided to upload challenges.")
        return

    logging.info(f"Uploading {challenge.name} to CTFd...")

    url = f"{config.ctfd_url}/api/v1/"
    headers = {"Authorization": f"Token {config.ctfd_token}", "Content-Type": "application/json"}

    response = requests.post(
        url + "challenges", headers=headers, json=challenge_to_ctfd(challenge, config, runner), timeout=60
    )
    if response.status_code != 200:
        logging.error(f"Failed to upload {challenge.name} to CTFd: {response.text}")
        return

    challenge_id = response.json()["data"]["id"]

    flag_data = {
        "challenge_id": challenge_id,
        "content": next(iter(challenge.flag.keys())),
        "type": "static",
        "data": "",
    }

    flag_response = requests.post(url + "flags", json=flag_data, headers=headers, timeout=60)
    if flag_response.status_code != 200:
        logging.error(f"Failed to upload flag for {challenge.name}: {flag_response.text}")
        return

    for hint in challenge.hints:
        hint_data = {
            "challenge_id": challenge_id,
            "content": hint,
            "type": "standard",
            "cost": 0,
        }
        hint_response = requests.post(url + "hints", json=hint_data, headers=headers, timeout=60)
        if hint_response.status_code != 200:
            logging.error(f"Failed to upload hint for {challenge.name}: {hint_response.text}")

    for tag in [challenge.difficulty, *challenge.tags]:
        tag_data = {
            "challenge_id": challenge_id,
            "value": tag,
        }

        tag_response = requests.post(url + "tags", json=tag_data, headers=headers, timeout=60)
        if tag_response.status_code != 200:
            logging.error(f"Failed to upload tag for {challenge.name}: {tag_response.text}")

    if not os.path.exists(challenge.path + "/Handout"):
        return

    # create a zip of the handouts and upload it as a file
    filename = f"{challenge.name.replace(' ', '_')}.zip"
    try:
        subprocess.run(
            ["zip", "-r", filename, "."],
            cwd=challenge.path + "/Handout",
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        logging.exception(f"Failed to create zip file for {challenge.name}")
        return

    file_path = os.path.join(challenge.path + "/Handout", filename)
    with open(file_path, "rb") as file:
        files = {"file": (filename, file)}
        file_response = requests.post(
            url + "files",
            headers=headers,
            files=files,
            data={"challenge_id": challenge_id, "type": "challenge"},
            timeout=60,
        )
        if file_response.status_code != 200:
            logging.error(f"Failed to upload handout for {challenge.name}: {file_response.text}")
    os.remove(file_path)
