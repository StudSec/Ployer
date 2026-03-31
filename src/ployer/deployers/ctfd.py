import hashlib
import json
import logging
import os
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import requests

from ployer.challenge import Challenge
from ployer.config import Config
from ployer.runners.base import ChallengeRunner

PLOYER_META_RE = re.compile(r"<!--\s*ployer-meta:(.*?)\s*-->", re.DOTALL)


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


def _file_hash(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dir_hash(path: Path) -> str:
    if not path.exists() or not path.is_dir():
        return ""

    hasher = hashlib.sha256()
    for item in sorted(path.rglob("*")):
        if item.is_file():
            rel = item.relative_to(path).as_posix()
            hasher.update(rel.encode("utf-8"))
            hasher.update(b"\0")
            hasher.update(item.read_bytes())
            hasher.update(b"\0")
    return hasher.hexdigest()


def _host_hash(ctfd_data: dict[str, Any]) -> str:
    host_keys = {
        "connection_info",
        "port",
        "timeout",
        "shared",
        "mana_cost",
        "destroy_on_flag",
        "scenario",
        "additional",
    }
    host_data = {k: v for k, v in ctfd_data.items() if k in host_keys}
    return hashlib.sha256(json.dumps(host_data, sort_keys=True).encode("utf-8")).hexdigest()


def _build_meta(challenge: Challenge, ctfd_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": 1,
        "challenge_toml_hash": _file_hash(Path(challenge.path) / "challenge.toml"),
        "handout_hash": _dir_hash(Path(challenge.path) / "Handout"),
        "host_hash": _host_hash(ctfd_data),
    }


def _description_with_meta(description: str, meta: dict[str, Any]) -> str:
    return f"{description}\n\n<!-- ployer-meta:{json.dumps(meta, sort_keys=True)} -->"


def _extract_meta(description: str | None) -> tuple[str, dict[str, Any] | None]:
    if not description:
        return "", None

    match = PLOYER_META_RE.search(description)
    if not match:
        return description, None

    clean_description = (description[: match.start()] + description[match.end() :]).rstrip()
    try:
        return clean_description, json.loads(match.group(1))
    except json.JSONDecodeError:
        return clean_description, None


def _get_all_challenges(url: str, headers: dict[str, str]) -> list[dict[str, Any]]:
    page = 1
    challenges: list[dict[str, Any]] = []

    while True:
        response = requests.get(url + "challenges", headers=headers, params={"page": page}, timeout=60)
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


def _get_challenge_detail(url: str, headers: dict[str, str], challenge_id: int) -> dict[str, Any] | None:
    response = requests.get(url + f"challenges/{challenge_id}", headers=headers, timeout=60)
    if response.status_code != 200:
        return None
    data = response.json().get("data")
    return data if isinstance(data, dict) else None


def _get_collection(url: str, headers: dict[str, str], resource: str, challenge_id: int) -> list[dict[str, Any]]:
    response = requests.get(url + resource, headers=headers, params={"challenge_id": challenge_id}, timeout=60)
    if response.status_code != 200:
        return []

    data = response.json().get("data", [])
    return data if isinstance(data, list) else []


def _core_challenge_hash(ctfd_data: dict[str, Any]) -> str:
    core_keys = {
        "name",
        "description",
        "category",
        "state",
        "type",
        "value",
        "initial",
        "decay",
        "minimum",
        "function",
    }
    core_data = {k: v for k, v in ctfd_data.items() if k in core_keys}
    return hashlib.sha256(json.dumps(core_data, sort_keys=True).encode("utf-8")).hexdigest()


def _challenge_content_synced(url: str, headers: dict[str, str], challenge: Challenge, challenge_id: int) -> bool:
    expected_flag = next(iter(challenge.flag.keys()))
    flags = _get_collection(url, headers, "flags", challenge_id)
    flag_ok = len(flags) == 1 and flags[0].get("content") == expected_flag and flags[0].get("type") == "static"

    expected_hints = sorted(challenge.hints)
    remote_hints = sorted(str(hint.get("content", "")) for hint in _get_collection(url, headers, "hints", challenge_id))
    hints_ok = expected_hints == remote_hints

    expected_tags = sorted([challenge.difficulty, *challenge.tags])
    remote_tags = sorted(str(tag.get("value", "")) for tag in _get_collection(url, headers, "tags", challenge_id))
    tags_ok = expected_tags == remote_tags

    return flag_ok and hints_ok and tags_ok


def _determine_update_state(
    url: str,
    headers: dict[str, str],
    challenge: Challenge,
    challenge_id: int,
    local_data_plain: dict[str, Any],
    local_meta: dict[str, Any],
    remote_challenge: dict[str, Any],
) -> tuple[bool, bool, bool, bool]:
    cleaned_remote_description, remote_meta = _extract_meta(remote_challenge.get("description"))
    if remote_meta == local_meta:
        return False, False, False, True

    remote_challenge_no_meta = dict(remote_challenge)
    remote_challenge_no_meta["description"] = cleaned_remote_description

    if remote_meta is not None:
        container_updated = remote_meta.get("host_hash") != local_meta["host_hash"]
        handout_updated = remote_meta.get("handout_hash") != local_meta["handout_hash"]
        challenge_toml_updated = remote_meta.get("challenge_toml_hash") != local_meta["challenge_toml_hash"]
    else:
        container_updated = _host_hash(remote_challenge_no_meta) != local_meta["host_hash"]
        handout_updated = True
        challenge_toml_updated = _core_challenge_hash(remote_challenge_no_meta) != _core_challenge_hash(
            local_data_plain
        ) or not _challenge_content_synced(url, headers, challenge, challenge_id)

    up_to_date = not container_updated and not handout_updated and not challenge_toml_updated
    return container_updated, handout_updated, challenge_toml_updated, up_to_date


def _upsert_flag(url: str, headers: dict[str, str], challenge: Challenge, challenge_id: int) -> None:
    desired = {
        "content": next(iter(challenge.flag.keys())),
        "type": "static",
        "data": "",
    }
    flags = _get_collection(url, headers, "flags", challenge_id)

    if not flags:
        payload = {"challenge_id": challenge_id} | desired
        response = requests.post(url + "flags", json=payload, headers=headers, timeout=60)
        if response.status_code != 200:
            logging.error(f"Failed to upload flag for {challenge.name}: {response.text}")
        return

    first_flag = flags[0]
    response = requests.patch(url + f"flags/{first_flag['id']}", json=desired, headers=headers, timeout=60)
    if response.status_code != 200:
        logging.error(f"Failed to patch flag for {challenge.name}: {response.text}")

    for extra_flag in flags[1:]:
        requests.delete(url + f"flags/{extra_flag['id']}", headers=headers, timeout=60)


def _replace_hints(url: str, headers: dict[str, str], challenge: Challenge, challenge_id: int) -> None:
    for hint in _get_collection(url, headers, "hints", challenge_id):
        requests.delete(url + f"hints/{hint['id']}", headers=headers, timeout=60)

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


def _replace_tags(url: str, headers: dict[str, str], challenge: Challenge, challenge_id: int) -> None:
    for tag in _get_collection(url, headers, "tags", challenge_id):
        requests.delete(url + f"tags/{tag['id']}", headers=headers, timeout=60)

    for tag in [challenge.difficulty, *challenge.tags]:
        tag_data = {
            "challenge_id": challenge_id,
            "value": tag,
        }

        tag_response = requests.post(url + "tags", json=tag_data, headers=headers, timeout=60)
        if tag_response.status_code != 200:
            logging.error(f"Failed to upload tag for {challenge.name}: {tag_response.text}")


def _replace_handout(url: str, headers: dict[str, str], challenge: Challenge, challenge_id: int) -> None:
    for file_item in _get_collection(url, headers, "files", challenge_id):
        requests.delete(url + f"files/{file_item['id']}", headers=headers, timeout=60)

    handout_path = Path(challenge.path) / "Handout"
    if not handout_path.exists() or not handout_path.is_dir():
        return

    filename = f"{challenge.name.replace(' ', '_')}.zip"
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        archive_path = Path(tmp.name)

    try:
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in sorted(handout_path.rglob("*")):
                if file_path.is_file():
                    zf.write(file_path, file_path.relative_to(handout_path).as_posix())

        with archive_path.open("rb") as file:
            files = {"file": (filename, file)}
            file_response = requests.post(
                url + "files",
                headers={"Authorization": headers["Authorization"]},
                files=files,
                data={"challenge_id": challenge_id, "type": "challenge"},
                timeout=60,
            )
            if file_response.status_code != 200:
                logging.error(f"Failed to upload handout for {challenge.name}: {file_response.text}")
    finally:
        os.remove(archive_path)


def upload_ctfd(challenge: Challenge, config: Config, runner: ChallengeRunner) -> None:
    if not config.ctfd_url or not config.ctfd_token:
        logging.error("CTFd URL and API key must be provided to upload challenges.")
        return

    logging.info(f"Uploading {challenge.name} to CTFd...")

    url = f"{config.ctfd_url}/api/v1/"
    headers = {"Authorization": f"Token {config.ctfd_token}", "Content-Type": "application/json"}
    local_data_plain = challenge_to_ctfd(challenge, config, runner)
    ctfd_data = dict(local_data_plain)
    local_meta = _build_meta(challenge, local_data_plain)
    ctfd_data["description"] = _description_with_meta(challenge.description, local_meta)

    existing = _find_challenge(url, headers, challenge.name)

    if existing:
        challenge_id = existing["id"]
        detail = _get_challenge_detail(url, headers, challenge_id)
        remote_challenge = detail or existing
        container_updated, handout_updated, challenge_toml_updated, up_to_date = _determine_update_state(
            url,
            headers,
            challenge,
            challenge_id,
            local_data_plain,
            local_meta,
            remote_challenge,
        )

        if up_to_date:
            logging.info(f"Skipping {challenge.name}: CTFd challenge is already up to date")
            return

        patch_response = requests.patch(url + f"challenges/{challenge_id}", headers=headers, json=ctfd_data, timeout=60)
        if patch_response.status_code != 200:
            logging.error(f"Failed to patch {challenge.name} on CTFd: {patch_response.text}")
            return

        if challenge_toml_updated:
            _upsert_flag(url, headers, challenge, challenge_id)
            _replace_hints(url, headers, challenge, challenge_id)
            _replace_tags(url, headers, challenge, challenge_id)

        if handout_updated:
            _replace_handout(url, headers, challenge, challenge_id)

        if container_updated:
            logging.info(f"Updated host/container data for {challenge.name} on CTFd")
        return

    response = requests.post(url + "challenges", headers=headers, json=ctfd_data, timeout=60)
    if response.status_code != 200:
        logging.error(f"Failed to upload {challenge.name} to CTFd: {response.text}")
        return

    challenge_id = response.json()["data"]["id"]
    _upsert_flag(url, headers, challenge, challenge_id)
    _replace_hints(url, headers, challenge, challenge_id)
    _replace_tags(url, headers, challenge, challenge_id)
    _replace_handout(url, headers, challenge, challenge_id)
