import argparse
import dataclasses
import json
import logging
import os
import subprocess
import threading
import collections
from dotenv import load_dotenv
import uvicorn
import yaml
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import requests
import time
from metrics import MetricsHandler
pending_commits = collections.defaultdict(set)


from prometheus_client import generate_latest


load_dotenv()

app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
class RepoToWatch:
    name: str
    branch: str
    path: str
    actions_need_to_pass: bool


@dataclasses.dataclass
class RepoUpdateResult:
    git_exit_code: int = 0
    docker_exit_code: int = 0
    development: bool = False
    git_stdout: str = ""
    git_stderr: str = ""
    docker_stdout: str = ""
    docker_stderr: str = ""


def load_config(development: bool):
    result = {}
    if development:
        return result
    with open("config.yml") as f:
        loaded_yaml = yaml.safe_load(f)
        for config in loaded_yaml.get("repos", []):
            parsed = RepoToWatch(**config)
            result[(parsed.name, parsed.branch)] = parsed

    return result


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--development", action="store_true")
    return parser.parse_args()


args = get_args()

config = load_config(args.development)


def push_update_success_as_discord_embed(
    repo_config: RepoToWatch, result: RepoUpdateResult
):
    repo_name = repo_config.name
    # default green
    color = 0x57F287
    if result.development:
        prefix = "[development mode]"
        repo_name = prefix + " " + repo_name
        # do a gray color if we are sending "not real" embeds
        color = 0x99AAB5

    embed_json = {
        "embeds": [
            {
                "title": f"{repo_name} was successfully updated",
                "url": "https://github.com/SCE-Development/"
                + repo_config.name,  # link to CICD project repo
                "description": "\n".join(
                    [
                        f"• git pull exited with code **{result.git_exit_code}**",
                        f"• git stdout: **```{result.git_stdout or 'No output'}```**",
                        f"• git stderr: **```{result.git_stderr or 'No output'}```**",
                        f"• docker-compose up exited with code **{result.docker_exit_code}**",
                        f"• docker-compose up stdout: **```{result.docker_stdout or 'No output'}```**",
                        f"• docker-compose up stderr: **```{result.docker_stderr or 'No output'}```**",
                    ]
                ),
                "color": color,
            }
        ]
    }
    try:
        discord_webhook = requests.post(
            str(os.getenv("CICD_DISCORD_WEBHOOK_URL")),
            json=embed_json,
        )
        if discord_webhook.status_code in (200, 204):
            return logger.info(f"Discord webhook response: {discord_webhook.text}")

        logger.error(
            f"Discord webhook returned status code: {discord_webhook.status_code} with text {discord_webhook.text}"
        )
    except Exception:
        logger.exception("push_update_success_as_discord_embed had a bad time")


def update_repo(repo_config: RepoToWatch) -> RepoUpdateResult:
    MetricsHandler.last_push_timestamp.labels(repo=repo_config.name).set(time.time())
    logger.info(
        f"updating {repo_config.name} to {repo_config.branch} in {repo_config.path}"
    )

    result = RepoUpdateResult()

    if args.development:
        logging.warning("skipping command to update, we are in development mode")
        result.development = True
        return push_update_success_as_discord_embed(repo_config, result)
    try:
        git_result = subprocess.run(
            ["git", "pull", "origin", repo_config.branch],
            cwd=repo_config.path,
            capture_output=True,
            text=True,
        )
        logger.info(f"Git pull stdout: {git_result.stdout}")
        logger.info(f"Git pull stderr: {git_result.stderr}")
        result.git_stdout = git_result.stdout
        result.git_stderr = git_result.stderr
        result.git_exit_code = git_result.returncode

        docker_result = subprocess.run(
            ["docker-compose", "up", "--build", "-d"],
            cwd=repo_config.path,
            capture_output=True,
            text=True,
        )
        logger.info(f"Docker compose stdout: {docker_result.stdout}")
        logger.info(f"Docker compose stdout: {docker_result.stderr}")
        result.docker_stdout = docker_result.stdout
        result.docker_stderr = docker_result.stderr
        result.git_exit_code = git_result.returncode
        push_update_success_as_discord_embed(repo_config, result)
    except Exception:
        logger.exception("update_repo had a bad time")


def handle_workflow_run(payload, repo_name):
    workflow_run = payload.get("workflow_run", {})
    status = workflow_run.get("status")
    conclusion = workflow_run.get("conclusion")
    head_commit = workflow_run.get("head_commit", {}).get("id")
    branch = workflow_run.get("head_branch")

    if head_commit not in pending_commits.get(repo_name, set()):
        return {
            "status": f"Not in pending_commits"
        } 
    
    if status != "completed" or conclusion != "success": 
        return {
            "status": f"Committed changes did not pass requirements. Status: {status}"
        }
    
    actions_need_to_pass = True
    commits = pending_commits.get(repo_name)
    if commits:
        pending_commits[repo_name].discard(head_commit)
    
    # check for any empty repos
    if not commits:
        pending_commits.pop(repo_name)
    
    ref = payload.get("ref", "")
    branch = ref.split("/")[-1]
    key = (repo_name, branch)

    if args.development and key not in config:
        # if we are in development mode, pretend that
        # we wanted to watch this repo no matter what
        config[key] = RepoToWatch(name=repo_name, branch=branch, path="/dev/null", actions_need_to_pass=actions_need_to_pass)

    if key not in config:
        logging.warning(f"not acting on repo and branch name of {key}")
        return {"status": f"not acting on repo and branch name of {key}"}
    
    logger.info(f"Push to {branch} detected for {repo_name}")
    # update the repo
    thread = threading.Thread(target=update_repo, args=(config[key],))
    thread.start()
    logger.info(f"Stored commit {head_commit} for repo {repo_name}")  # <-- log here

    return {"status": "webhook received"}



@app.post("/webhook")
async def github_webhook(request: Request):
    MetricsHandler.last_smee_request_timestamp.set(time.time())
    payload_body = await request.body()
    payload = json.loads(payload_body)
    event_header = request.headers.get("X-GitHub-Event")
    repo_name = payload.get("repository", {}).get("name")
    actions_need_to_pass = False
    
    if (not repo_name):
        return {"status": "missing repo name"}

    if event_header == "push":
        head_commit = payload.get("head_commit", {}).get("id")
        if not head_commit:
            return {"status": "missing head_commit"}
        pending_commits[repo_name].add(head_commit)
        logger.info(f"Stored {head_commit} for {repo_name}")
        
        return {
            "status": f"commit recorded"
        }
    
    elif event_header == "workflow_run":
        handle_workflow_run(payload, repo_name)
        
    else: 
        return {
            "status": f"X-GitHub-Event header was not set to a valid event, got value {event_header}"
        }


@app.get("/metrics")
def get_metrics():
    return Response(
        media_type="text/plain",
        content=generate_latest(),
    )


@app.get("/")
def read_root():
    return {"message": "SCE CICD Server"}


def start_smee():
    try:
        # sends the smee command to the tmux session named smee
        smee_cmd = [
            "npx",
            "smee",
            "--url",
            os.getenv("SMEE_URL"),
            "--target",
            "http://127.0.0.1:3000/webhook",
        ]

        process = subprocess.Popen(
            smee_cmd,
        )
        logger.info(f"smee started with PID {process.pid}")
    except Exception:
        logger.exception("Error starting smee")


if __name__ == "server":
    MetricsHandler.init()

if __name__ == "__main__":
    start_smee()
    uvicorn.run("server:app", port=3000, reload=True)
