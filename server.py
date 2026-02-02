import argparse
import dataclasses
import getpass
import json
import logging
import os
import re
import socket
import subprocess
import time
from typing import Dict, List, Optional, Tuple

import requests
import uvicorn
import yaml
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from metrics import MetricsHandler
from prometheus_client import generate_latest

load_dotenv()

logging.basicConfig(
    # in mondo we trust
    format="%(asctime)s.%(msecs)03dZ %(threadName)s %(levelname)s:%(name)s:%(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    level=logging.INFO,
)
logging.getLogger("uvicorn.access").setLevel(logging.ERROR)
logging.getLogger("uvicorn.error").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class RepoConfig:
    name: str
    branch: str
    path: str
    # list of all the containers
    # makes sure theres a new list made for each repotowatch object
    containers_to_force_recreate: List[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class ExecutionResult:
    command: str
    exit_code: int = 1
    stdout: str = ""
    stderr: str = ""
    success: bool = False


@dataclasses.dataclass
class DeploymentStatus:
    repo: str
    branch: str
    commit_id: str = "commit_id not set"
    commit_msg: str = "commit_msg not set"
    author: str = "author not set"
    git_execution_result: Optional[ExecutionResult] = None
    docker_execution_result: Optional[ExecutionResult] = None
    docker_force_execution_result: Optional[ExecutionResult] = None
    is_dev: bool = False


def get_args():
    parser = argparse.ArgumentParser(description="SCE CICD Server")
    parser.add_argument(
        "--development",
        action="store_true",
        help="Run in dev mode (no shell execution)",
    )
    parser.add_argument(
        "--port", type=int, default=3000, help="Port to run the server on"
    )
    parser.add_argument(
        "--config",
        default="config.yml",
        help="path to config file, defaults to ./config.yml",
    )
    return parser.parse_args()


def run_command(args: list, cwd: str) -> ExecutionResult:
    cmd_str = " ".join(args)
    try:
        process = subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, timeout=300
        )
        return ExecutionResult(
            command=cmd_str,
            exit_code=process.returncode,
            stdout=process.stdout.strip(),
            stderr=process.stderr.strip(),
            success=(process.returncode == 0),
        )
    except Exception:
        logger.exception(f"Failed to execute {cmd_str}")
        return ExecutionResult(command=cmd_str)


def send_notification(status: DeploymentStatus):
    webhook_url = os.getenv("CICD_DISCORD_WEBHOOK_URL")
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


def get_docker_images_disk_usage_bytes():
    # Docker uses SI units: 1000^n
    UNIT_MAP = {
        'B': 1,
        'KB': 10**3, 'KB': 10**3, 
        'MB': 10**6, 'MB': 10**6,
        'GB': 10**9, 'GB': 10**9,
        'TB': 10**12
    }
    try:
        # Get docker system df output as JSON lines
        result = subprocess.run(
            ["docker", "system", "df", "--format", "{{json .}}"],
            capture_output=True, text=True, check=True
        )
        for line in result.stdout.splitlines():
            data = json.loads(line)
            if data.get("Type") != "Images":
                continue

            raw_size = data.get("Size", "")  # e.g., "8.423GB"
            match = re.match(r"([0-9.]+)\s*([a-zA-Z]+)", raw_size)
            if not match:
                logger.info("could not extract image disk usage from docker response of {raw_size}")
                return None
            
            number, unit = match.groups()
            # Normalize unit to uppercase for the map
            multiplier = UNIT_MAP.get(unit.upper(), 1)
            
            return int(float(number) * multiplier)

        return None
    except Exception:
        logger.exception("Error getting Docker image disk usage")


def handle_deploy(repo_cfg: RepoConfig, payload: dict, is_dev: bool):
    MetricsHandler.last_push_timestamp.labels(repo=repo_cfg.name).set(time.time())

    commit = payload.get("head_commit") or {}
    status = DeploymentStatus(
        repo=repo_cfg.name,
        branch=repo_cfg.branch,
        commit_id=commit.get("id", "unknown"),
        commit_msg=commit.get("message", "No message"),
        author=commit.get("author", {}).get("username", "unknown"),
        is_dev=is_dev,
    )

    if is_dev:
        logger.info(f"Skipping shell execution for {repo_cfg.name} (Dev Mode)")
        send_notification(status)
        return

    logger.info(f"Starting deployment for {repo_cfg.name}:{repo_cfg.branch}")

    # Git Pull
    status.git_execution_result = run_command(
        ["git", "pull", "origin", repo_cfg.branch], repo_cfg.path
    )
    if not status.git_execution_result.success:
        logger.error(f"Git pull failed for {repo_cfg.name}")
        send_notification(status)
        return

    # Docker Compose
    status.docker_execution_result = run_command(
        ["docker-compose", "up", "--build", "-d"], repo_cfg.path
    )

    if repo_cfg.containers_to_force_recreate:
        command = ["docker-compose", "up", "--build", "-d", "--force-recreate", "--no-deps"]
        command.extend(repo_cfg.containers_to_force_recreate)
        status.docker_force_execution_result = run_command(command, repo_cfg.path)

    logger.error(f"deployment complete for {repo_cfg.name}:{repo_cfg.branch}")
    send_notification(status)
    get_docker_images_disk_usage_bytes()


def push_skipped_update_as_discord_embed(
    repo_config: RepoConfig, incoming_branch: str, local_branch: str
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
            os.getenv("CICD_DISCORD_WEBHOOK_URL"),
            json=embed_json,
            timeout=10
        )
        response.raise_for_status()
        logger.info(f"Mismatch notification sent for {repo_name}")
    except Exception:
        logger.exception("Failed to send mismatch notification to Discord")

app = FastAPI()
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

args = get_args()
REPO_MAP: Dict[Tuple[str, str], RepoConfig] = {}

# dis one loads the config.yml file
# turns it into a dictionary
# result is the dictionary
try:
    if not args.development:
        with open(args.config) as f:
            raw_repos = yaml.safe_load(f).get("repos", [])
            for r in raw_repos:
                # make a new entry into the result dictionary
                # the key is a tuple of the repo name and branch
                # the value is a RepoToWatch object
                cfg = RepoConfig(**r)
                REPO_MAP[(cfg.name, cfg.branch)] = cfg
except Exception:
    logger.exception(f"Failed to load config at path {args.config}")


@app.post("/webhook")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    MetricsHandler.last_smee_request_timestamp.set(time.time())

    event = request.headers.get("X-GitHub-Event")
    if event != "push":
        return {"status": "ignored", "reason": f"Event {event} is not 'push'"}

    payload = await request.json()
    branch = payload.get("ref", "").split("/")[-1]
    repo_name = payload.get("repository", {}).get("name")
    key = (repo_name, branch)

    # Resolve target config
    target = REPO_MAP.get(key)
    if not target:
        logger.warning(f"No configuration found for {repo_name}:{branch}")
        return {"status": "ignored", "reason": "Repository/Branch not tracked"}

    if not args.development:
        current_branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=target.path,
            capture_output=True,
            text=True,
        )
        current_branch = current_branch_result.stdout.strip()

        if current_branch != branch:
            logger.warning(f"Branch mismatch for {repo_name}")
            # Update the call to pass both branches
            push_skipped_update_as_discord_embed(target, branch, current_branch)
            return {"status": "skipped", "reason": "branch mismatch"}

    logger.info(f"Accepted push for {repo_name}:{branch}")
    background_tasks.add_task(handle_deploy, target, payload, args.development)
    return {"status": "accepted"}


@app.get("/metrics")
def get_metrics():
    return Response(media_type="text/plain", content=generate_latest())


@app.get("/")
def health():
    return {"status": "ok", "dev_mode": args.development}


def start_smee():
    url = os.getenv("SMEE_URL")
    if not url:
        return

    target = f"http://127.0.0.1:{args.port}/webhook"
    try:
        proc = subprocess.Popen(
            ["npx", "smee", "--url", url, "--target", target], stdout=subprocess.DEVNULL
        )
        logger.info(f"Smee client started (PID: {proc.pid}) targeting {target}")
    except Exception:
        logger.exception("Failed to start smee client")


if __name__ == "server":
    MetricsHandler.init()
    usage = get_docker_images_disk_usage_bytes()
    if usage is not None:
        MetricsHandler.docker_image_disk_usage_bytes.set(usage)

if __name__ == "__main__":
    start_smee()
    uvicorn.run("server:app", port=args.port, reload=True)
