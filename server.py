import dataclasses
import json
import logging
import os
import subprocess
import threading

from dotenv import load_dotenv
import uvicorn
import yaml
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import requests
import time
from metrics import MetricsHandler


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


def load_config():
    result = {}
    with open("config.yml") as f:
        loaded_yaml = yaml.safe_load(f)
        for config in loaded_yaml.get("repos", []):
            parsed = RepoToWatch(**config)
            result[(parsed.name, parsed.branch)] = parsed

    return result


config = load_config()


def update_repo(repo_config: RepoToWatch):
    MetricsHandler.last_push_timestamp.labels(repo=repo_config.name).set(time.time())
    logger.info(
        f"updating {repo_config.name} to {repo_config.branch} in {repo_config.path}"
    )
    try:
        git_result = subprocess.run(
            ["git", "pull", "origin", repo_config.branch], cwd=repo_config.path
        )
        logger.info(f"Git pull stdout: {git_result.stdout}")
        logger.info(f"Git pull stderr: {git_result.stderr}")

        docker_result = subprocess.run(
            ["docker-compose", "up", "--build", "-d"], cwd=repo_config.path
        )
        logger.info(f"Docker compose stdout: {docker_result.stdout}")
        logger.info(f"Docker compose stdout: {docker_result.stderr}")
        if docker_result.returncode != 0:
            logger.error(
                f"Docker compose exited with nonzero status: {docker_result.returncode}"
            )
        discord_webhook = requests.post(
            str(os.getenv("CICD_DISCORD_WEBHOOK_URL")),
            json={
                "content": f"successfuly redeployed {repo_config.name} to {repo_config.branch} in {repo_config.path}"
            },
        )
        if discord_webhook.status_code not in (200, 204):
            logger.error(
                f"Discord webhook failed with status code: {discord_webhook.status_code}"
            )
        else:
            logger.info(f"Discord webhook response: {discord_webhook.text}")
    except Exception:
        logger.exception("update_repo had a bad time")


@app.post("/webhook")
async def github_webhook(request: Request):
    MetricsHandler.last_smee_request_timestamp.set(time.time())
    payload_body = await request.body()
    payload = json.loads(payload_body)

    event_header = request.headers.get("X-GitHub-Event")
    # check if this is a push event
    if event_header != "push":
        return {
            "status": f"X-GitHub-Event header was not set to push, got value {event_header}"
        }

    ref = payload.get("ref", "")
    branch = ref.split("/")[-1]
    repo_name = payload.get("repository", {}).get("name")

    key = (repo_name, branch)
    if key not in config:
        return {"status": f"not acting on repo and branch name of {key}"}

    logger.info(f"Push to {branch} detected for {repo_name}")
    # update the repo
    thread = threading.Thread(target=update_repo, args=(config[key],))
    thread.start()

    return {"status": "webhook received"}


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
    start_smee()

if __name__ == "__main__":
    uvicorn.run("server:app", port=3000, reload=True)
