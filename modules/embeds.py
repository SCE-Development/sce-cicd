import getpass
import logging
import socket
from typing import List

import requests

from modules.structs import DeploymentStatus, RepoConfig

logger = logging.getLogger(__name__)


def send_notification(status: DeploymentStatus, webhook_url: str):
    if not webhook_url:
        logger.warning("Discord webhook URL missing from environment")
        return

    # Default to failure/neutral
    color = 0xED4245
    title = "Deployment Failed"

    if status.is_dev:
        color = 0x99AAB5
        title = "[Development Mode]"
    elif not status.git_execution_result or status.git_execution_result.success:
        color = 0x57F287
        title = "Deployment Successful"

    env_str = f"{getpass.getuser()}@{socket.gethostname()}"

    commit_id_to_use = status.commit_id

    # assume it's an actual commit so we truncate it to the first 7
    if " " not in status.commit_id and status.commit_id is not None:
        commit_id_to_use = status.commit_id[:7]

    description = (
        f"**Repo:** `{status.repo}:{status.branch}`\n"
        f"**Commit:** `{commit_id_to_use}` — {status.commit_msg}\n"
        f"**Author:** {status.author} | **Host:** `{env_str}`\n"
    )

    for execution_result in [
        status.git_execution_result,
        status.docker_execution_result,
        status.docker_force_execution_result,
    ]:
        if not execution_result:
            continue
        icon = "✅" if execution_result.success else "⚠️"
        description += f"\n{icon} `{execution_result.command}` (Exit: {execution_result.exit_code})"
        if execution_result.stderr:
            description += f"\n```stderr\n{execution_result.stderr}```"

    payload = {"embeds": [{"title": title, "description": description, "color": color}]}
    try:
        requests.post(webhook_url, json=payload, timeout=10).raise_for_status()
    except Exception:
        logger.exception("Failed to send Discord notification")


def push_skipped_update_as_discord_embed_mismatched_branch(
    repo_config: RepoConfig, incoming_branch: str, local_branch: str, webhook_url: str
):
    repo_name = repo_config.name
    # Yellow warning color
    color = 0xFFFF00

    # Get user@hostname
    env_str = f"{getpass.getuser()}@{socket.gethostname()}"

    description = (
        f"**Incoming Push:** `{incoming_branch}`\n"
        f"**Local Branch:** `{local_branch}`\n"
        f"**Path:** `{repo_config.path}`\n"
        f"**Host:** `{env_str}`"
    )

    embed_json = {
        "embeds": [
            {
                "title": "Branch Mismatch: Deployment Skipped",
                "url": f"https://github.com/SCE-Development/{repo_name}",
                "description": description,
                "color": color,
                "footer": {
                    "text": "The local branch must match the pushed branch to trigger CI/CD."
                }
            }
        ]
    }

    try:
        response = requests.post(
            webhook_url,
            json=embed_json,
            timeout=10
        )
        response.raise_for_status()
        logger.info(f"Mismatch notification sent for {repo_name}")
    except Exception:
        logger.exception("Failed to send mismatch notification to Discord")


def push_skipped_update_as_discord_embed_docker_ignore(
    repo_cfg: RepoConfig, files_changed: List[str], webhook_url: str
):
    if not webhook_url:
        logger.info("skipping docker embed, cicd_discord_webhook_url is empty")
        return

    # A neutral Blue/Grey color for "Informational"
    color = 0x3498db
    title = "Deployment Skipped (Ignored Files)"

    # Truncate file list if it's too long for Discord
    files_display = "\n".join(files_changed[:10])
    if len(files_changed) > 10:
        files_display += f"\n*...and {len(files_changed) - 10} more*"

    patterns_display = ", ".join([f"`{p}`" for p in repo_cfg.docker_ignore])
    env_str = f"{getpass.getuser()}@{socket.gethostname()}"

    description = (
        f"**Repo:** `{repo_cfg.name}:{repo_cfg.branch}`\n"
        f"**Status:** No deployment triggered because all changed files match the `docker_ignore` patterns.\n\n"
        f"**Matched Patterns:** {patterns_display}\n"
        f"**Files Changed:**\n```\n{files_display}\n```\n"
        f"**Host:** `{env_str}`"
    )

    payload = {
        "embeds": [{
            "title": title,
            "description": description,
            "color": color,
            "footer": {"text": "CICD Engine • Filtered by docker_ignore"}
        }]
    }

    try:
        requests.post(webhook_url, json=payload, timeout=10)
    except Exception:
        logger.exception("Failed to send skip notification")
