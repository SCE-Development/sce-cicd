import argparse
import getpass
import logging
import os
import socket
import subprocess
import sys
import time
from typing import Dict, Optional, Tuple

import requests
import uvicorn
import yaml
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from metrics import MetricsHandler
from prometheus_client import generate_latest

load_dotenv()

# We include funcName here so we don't have to manually label logs
LOG_FORMAT = (
    "%(asctime)s.%(msecs)03dZ [%(levelname)s] %(name)s:%(funcName)s: %(message)s"
)
logging.basicConfig(format=LOG_FORMAT, datefmt="%Y-%m-%dT%H:%M:%S", level=logging.INFO)
logging.getLogger("uvicorn.access").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)


class RepoConfig(BaseModel):
    name: str
    branch: str
    path: str


class ExecutionResult(BaseModel):
    command: str
    exit_code: int = 1
    stdout: str = ""
    stderr: str = ""
    success: bool = False


class DeploymentStatus(BaseModel):
    repo: str
    branch: str
    commit_id: str = "unknown"
    commit_msg: str = "N/A"
    author: str = "unknown"
    git_res: Optional[ExecutionResult] = None
    docker_res: Optional[ExecutionResult] = None
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
    elif not status.git_res or status.git_res.success:
        color = 0x57F287
        title = "Deployment Successful"

    env_str = f"{getpass.getuser()}@{socket.gethostname()}"
    description = (
        f"**Repo:** `{status.repo}:{status.branch}`\n"
        f"**Commit:** `{status.commit_id[:7]}` — {status.commit_msg}\n"
        f"**Author:** {status.author} | **Host:** `{env_str}`\n"
    )

    for res in [status.git_res, status.docker_res]:
        if not res:
            continue
        icon = "✅" if res.success else "⚠️"
        description += f"\n{icon} `{res.command}` (Exit: {res.exit_code})"
        if res.stderr:
            description += f"\n```stderr\n{res.stderr[:250]}```"

    payload = {"embeds": [{"title": title, "description": description, "color": color}]}
    try:
        requests.post(webhook_url, json=payload, timeout=10).raise_for_status()
    except Exception:
        logger.exception("Failed to send Discord notification")


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
    status.git_res = run_command(
        ["git", "pull", "origin", repo_cfg.branch], repo_cfg.path
    )
    if not status.git_res.success:
        logger.error(f"Git pull failed for {repo_cfg.name}")
        send_notification(status)
        return

    # Docker Compose
    status.docker_res = run_command(
        ["docker-compose", "up", "--build", "-d"], repo_cfg.path
    )

    send_notification(status)


app = FastAPI()
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

ARGS = get_args()
REPO_MAP: Dict[Tuple[str, str], RepoConfig] = {}

# Load config once at startup
try:
    if not ARGS.development:
        with open("config.yml") as f:
            raw_repos = yaml.safe_load(f).get("repos", [])
            for r in raw_repos:
                cfg = RepoConfig(**r)
                REPO_MAP[(cfg.name, cfg.branch)] = cfg
except Exception:
    logger.exception("Failed to load config.yml")


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
    if ARGS.development:
        target = target or RepoConfig(name=repo_name, branch=branch, path="/dev/null")

    if not target:
        logger.warning(f"No configuration found for {repo_name}:{branch}")
        return {"status": "ignored", "reason": "Repository/Branch not tracked"}

    logger.info(f"Accepted push for {repo_name}:{branch}")
    background_tasks.add_task(handle_deploy, target, payload, ARGS.development)
    return {"status": "accepted"}


@app.get("/metrics")
def get_metrics():
    return Response(media_type="text/plain", content=generate_latest())


@app.get("/")
def health():
    return {"status": "ok", "dev_mode": ARGS.development}


def start_smee():
    url = os.getenv("SMEE_URL")
    if not url:
        return

    target = f"http://127.0.0.1:{ARGS.port}/webhook"
    try:
        proc = subprocess.Popen(
            ["npx", "smee", "--url", url, "--target", target], stdout=subprocess.DEVNULL
        )
        logger.info(f"Smee client started (PID: {proc.pid}) targeting {target}")
    except Exception:
        logger.exception("Failed to start smee client")

if __name__ == "server":
    MetricsHandler.init()

if __name__ == "__main__":
    start_smee()
    uvicorn.run("server:app", port=ARGS.port, reload=True)
