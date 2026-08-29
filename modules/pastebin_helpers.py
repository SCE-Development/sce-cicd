import logging
from urllib.parse import urljoin

import requests


def build_execution_log(
    command: str,
    stdout: str | None,
    stderr: str | None,
) -> str:
    log_parts = [f"# {command}", ""]

    if stdout:
        log_parts.append(stdout.strip())

    if stderr:
        log_parts.append(stderr.strip())

    if not stdout and not stderr:
        log_parts.append("(no output)")

    return "\n".join(log_parts)


def create_paste(
    developer_key: str,
    step_title: str,
    content: str,
    timeout_seconds: float = 15.0,
) -> str | None:
    if not developer_key.strip():
        logging.warning("Pastebin API Key is empty")
        return None

    create_url = "https://sce.sjsu.edu/p/create"

    headers = {
        "Content-Type": "application/json",
        "X-API-Key": developer_key.strip(),
    }

    payload = {
        "title": step_title,
        "text": content,
    }

    response = requests.post(
        create_url,
        json=payload,
        headers=headers,
        timeout=timeout_seconds,
    )

    response.raise_for_status()

    try:
        data = response.json()
    except requests.exceptions.JSONDecodeError:
        logging.exception(f"cannot decode JSON for {step_title}")
        return None

    get_paste_base_url = "https://sce.sjsu.edu/p/"
    # extract the relative id (e.g., "2890b") and combine it with the base domain
    paste_id = data.get("id")
    if not paste_id:
        logging.error(f"for step {step_title}, response JSON missing 'id' field: {data}")
        return None

    return urljoin(create_url, paste_id)
