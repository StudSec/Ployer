import logging
import os
import subprocess
from pathlib import Path
from typing import Any

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


def _get_all_challenges(url: str, headers: dict[str, str]) -> list[dict[str, Any]]:
    page = 1
    challenges: list[dict[str, Any]] = []

    while True:
        response = requests.get(url + "challenges", headers=headers, params={"page": page}, timeout=600)
        if response.status_code != 200:
            break

        payload = response.json()
        data = payload.get("data", [])
        if not data:
            break

        challenges.extend(data)
        next_page = payload.get("meta", {}).get("pagination", {}).get("next")
        if not next_page:
            break
        page += 1

    return challenges


def _find_challenge(url: str, headers: dict[str, str], name: str) -> dict[str, Any] | None:
    for item in _get_all_challenges(url, headers):
        if item.get("name") == name:
            return item
    return None


def _get_collection(url: str, headers: dict[str, str], resource: str, challenge_id: int) -> list[dict[str, Any]]:
    response = requests.get(url + resource, headers=headers, params={"challenge_id": challenge_id}, timeout=600)
    if response.status_code != 200:
        return []

    data = response.json().get("data", [])
    return data if isinstance(data, list) else []


def _upsert_flag(url: str, headers: dict[str, str], challenge: Challenge, challenge_id: int) -> None:
    desired = {
        "content": next(iter(challenge.flag.keys())),
        "type": "static",
        "data": "",
    }
    flags = _get_collection(url, headers, "flags", challenge_id)

    if not flags:
        payload = {"challenge_id": challenge_id} | desired
        response = requests.post(url + "flags", json=payload, headers=headers, timeout=600)
        if response.status_code != 200:
            logging.error(f"Failed to upload flag for {challenge.name}: {response.text}")
        return

    first_flag = flags[0]
    response = requests.patch(url + f"flags/{first_flag['id']}", json=desired, headers=headers, timeout=600)
    if response.status_code != 200:
        logging.error(f"Failed to patch flag for {challenge.name}: {response.text}")

    for extra_flag in flags[1:]:
        requests.delete(url + f"flags/{extra_flag['id']}", headers=headers, timeout=600)


def _replace_hints(url: str, headers: dict[str, str], challenge: Challenge, challenge_id: int) -> None:
    for hint in _get_collection(url, headers, "hints", challenge_id):
        requests.delete(url + f"hints/{hint['id']}", headers=headers, timeout=600)

    for hint in challenge.hints:
        hint_data = {
            "challenge_id": challenge_id,
            "content": hint,
            "type": "standard",
            "cost": 0,
        }
        hint_response = requests.post(url + "hints", json=hint_data, headers=headers, timeout=600)
        if hint_response.status_code != 200:
            logging.error(f"Failed to upload hint for {challenge.name}: {hint_response.text}")


def _replace_tags(url: str, headers: dict[str, str], challenge: Challenge, challenge_id: int) -> None:
    for tag in _get_collection(url, headers, "tags", challenge_id):
        requests.delete(url + f"tags/{tag['id']}", headers=headers, timeout=600)

    for tag in [challenge.difficulty, *challenge.tags]:
        tag_data = {
            "challenge_id": challenge_id,
            "value": tag,
        }

        tag_response = requests.post(url + "tags", json=tag_data, headers=headers, timeout=600)
        if tag_response.status_code != 200:
            logging.error(f"Failed to upload tag for {challenge.name}: {tag_response.text}")


def _replace_handout(url: str, headers: dict[str, str], challenge: Challenge, challenge_id: int) -> None:
    handout_path = Path(challenge.path) / "Handout"
    if not handout_path.exists() or not handout_path.is_dir():
        return

    # create a zip of the handouts and upload it as a file
    filename = f"{challenge.name.replace(' ', '_')}.zip"

    for file_item in _get_collection(url, headers, "files", challenge_id):
        if filename in file_item.get("location", ""):
            requests.delete(url + f"files/{file_item['id']}", headers=headers, timeout=600)
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
        file_response = requests.post(
            url + "files",
            headers={"Authorization": headers["Authorization"]},
            files=[("file", (filename, file, "application/zip"))],
            data={"challenge_id": challenge_id, "type": "challenge"},
            timeout=600,
        )
        if file_response.status_code != 200:
            logging.error(f"Failed to upload handout for {challenge.name}: {file_response.text}")
    os.remove(file_path)


def upload_ctfd(challenge: Challenge, config: Config, runner: ChallengeRunner) -> None:
    if not config.ctfd_url or not config.ctfd_token:
        logging.error("CTFd URL and API key must be provided to upload challenges.")
        return

    logging.info(f"Uploading {challenge.name} to CTFd...")

    url = f"{config.ctfd_url}/api/v1/"
    headers = {"Authorization": f"Token {config.ctfd_token}", "Content-Type": "application/json"}
    ctfd_data = challenge_to_ctfd(challenge, config, runner)

    existing = _find_challenge(url, headers, challenge.name)

    if existing:
        # Challenge exists, update it
        challenge_id = existing["id"]
        patch_response = requests.patch(url + f"challenges/{challenge_id}", headers=headers, json=ctfd_data, timeout=600)
        if patch_response.status_code != 200:
            logging.error(f"Failed to patch {challenge.name} on CTFd: {patch_response.text}")
            return
    else:
        # Challenge doesn't exist, create it
        response = requests.post(url + "challenges", headers=headers, json=ctfd_data, timeout=600)
        if response.status_code != 200:
            logging.error(f"Failed to upload {challenge.name} to CTFd: {response.text}")
            return
        challenge_id = response.json()["data"]["id"]

    _upsert_flag(url, headers, challenge, challenge_id)
    _replace_hints(url, headers, challenge, challenge_id)
    _replace_tags(url, headers, challenge, challenge_id)
    _replace_handout(url, headers, challenge, challenge_id)
    logging.info(f"Uploaded {challenge.name} to CTFd")
