import dataclasses
import datetime
import fnmatch
import json
import logging
import os
import queue
import re
import subprocess
import threading
import time
from typing import Dict, List, Optional, Tuple

from fastapi import BackgroundTasks, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import generate_latest
import uvicorn
import websocket
import yaml

from metrics import MetricsHandler
from modules.args import get_args
from modules.commit_status_helpers import CommitStatus, push_commit_status
from modules.embeds import (
    push_skipped_update_as_discord_embed_docker_ignore,
    push_skipped_update_as_discord_embed_mismatched_branch,
    send_notification,
)
from modules.pastebin_helpers import build_execution_log, create_paste
from modules.structs import (
    DeploymentStatus,
    ExecutionResult,
    RepoConfig,
    Smee2ListenResult,
)


args = get_args()
logging.basicConfig(
    # in mondo we trust
    format="%(asctime)s.%(msecs)03dZ %(threadName)s %(levelname)s:%(name)s:%(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    level=logging.ERROR - (args.verbose * 10),
)
logging.getLogger("uvicorn.access").setLevel(logging.ERROR)
logging.getLogger("uvicorn.error").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)

# perhaps we create a separate handler for threads
# a queue for repo and branch
# every webhook call adds it to the queue for repo and branch
# we built dis city
# we built dis city on queues and threads
REPO_QUEUES: Dict[Tuple[str, str], queue.Queue] = {}

# A Lock to ensure we don't create two threads for the same repo at once
THREAD_MANAGER_LOCK = threading.Lock()

# Track which repos have an active worker thread
ACTIVE_WORKERS: set = set()

# this stuff gets loaded from config.yml, see readme
SMEE2_URL = None
SMEE2_API_KEY = None
CICD_DISCORD_WEBHOOK_URL = None
GITHUB_TOKEN = None
PASTEBIN_API_KEY = None
PUSHGATEWAY_URL = None


REQUIRED_REPO_FIELDS = {
    f.name for f in dataclasses.fields(RepoConfig)
    if f.default == dataclasses.MISSING and f.default_factory == dataclasses.MISSING
}


def validate_config(repo: dict):
    missing = REQUIRED_REPO_FIELDS - repo.keys()
    if missing:
        raise SystemExit(f"[config] Repo '{repo.get('name', '?')}' is missing fields: {missing}")
    if not os.path.isdir(repo["path"]):
        raise SystemExit(f"[config] Path does not exist for repo '{repo['name']}': {repo['path']}")
    unknown_fields = repo.keys() - {f.name for f in dataclasses.fields(RepoConfig)} # set of all fields in RepoConfig
    if unknown_fields:
        logger.warning(f"[config] Repo '{repo.get('name', '?')}' has unknown fields: {unknown_fields}")
        return unknown_fields




def run_command(command_args: list, cwd: str) -> ExecutionResult:
    cmd_str = " ".join(command_args)
    
    if args.development:
        logger.info(f"mocking execution of \"{cmd_str}\" due to --development flag")
        return ExecutionResult(
            command=cmd_str,
            exit_code=0,
            stdout=f"{cmd_str} output would be here",
            stderr="",
            success=True
        )

    try:
        process = subprocess.run(
            command_args, cwd=cwd, capture_output=True, text=True, timeout=300
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


def push_github_commit_status(status: DeploymentStatus):
    if status.is_dev:
        logger.info("Development mode: Skipping GitHub notification")
        return
    if not GITHUB_TOKEN:
        logger.warning("GitHub token missing from environment")
        return
    if not status.commit_id or status.commit_id == "unknown": 
        logger.warning("Cannot push GitHub status because commit ID is missing")
        return

    execution_results = [
        ('Git Pull', 'git_execution_result', ),
        ('Docker Build', 'docker_execution_result', ),
    ]

    if getattr(status, 'docker_force_execution_result', None) is not None:
        execution_results.extend([
            ('Docker Force Recreate', 'docker_force_execution_result', ),
        ])

    for step_title, status_field_name in execution_results:
        execution_result = getattr(status, status_field_name, None)
        deployment_failed = execution_result is not None and not execution_result.success 

        paste_url = None 

        if PASTEBIN_API_KEY is not None:
            try:
                paste_url = create_paste(
                    developer_key = PASTEBIN_API_KEY,
                    step_title=step_title,
                    content =  build_execution_log(
                        command=execution_result.command,
                        stdout=execution_result.stdout,
                        stderr=execution_result.stderr,
                    ),
                )
                logger.info(f"{step_title} logs uploaded to Pastebin")
            except Exception:
                logger.exception(
                    f"Failed to upload {step_title} logs to Pastebin"
                )

        commit_status = CommitStatus(
            state = "failure" if deployment_failed else "success", 
            description=(
                "Deployment failed" 
                if deployment_failed
                else "Deployment successful"
            ), 
            context = f"[sce-cicd] {step_title}", 
            target_url = paste_url, 
        )
        
        try: 
            push_commit_status(
                owner = "SCE-Development", 
                repo = status.repo, 
                sha = status.commit_id, 
                token = GITHUB_TOKEN, 
                status = commit_status, 
            )
            logger.info("GitHub commit status pushed successfully") 
        except Exception: 
            logger.exception("Failed to push GitHub commit status")


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
            usage = int(float(number) * multiplier)
            MetricsHandler.docker_image_disk_usage_bytes.set(usage)
            MetricsHandler.push(PUSHGATEWAY_URL)

        return None
    except Exception:
        logger.exception("Error getting Docker image disk usage")


def handle_deploy(repo_cfg: RepoConfig, payload: dict, is_dev: bool):
    MetricsHandler.last_push_timestamp.labels(repo=repo_cfg.name).set(time.time())
    MetricsHandler.push(PUSHGATEWAY_URL)

    commit = payload.get("head_commit") or {}
    status = DeploymentStatus(
        repo=repo_cfg.name,
        branch=repo_cfg.branch,
        commit_id=commit.get("id", "unknown"),
        commit_msg=commit.get("message", "No message"),
        author=commit.get("author", {}).get("username", "unknown"),
        is_dev=is_dev,
    )

    logger.info(f"Starting deployment for {repo_cfg.name}:{repo_cfg.branch}")

    backup_branch = None
    if repo_cfg.enable_rollback and not is_dev:
        backup_branch = create_backup_branch(repo_cfg)

    # Git Pull
    status.git_execution_result = run_command(
        ["git", "pull", "origin", repo_cfg.branch], repo_cfg.path
    )
    if not status.git_execution_result.success:
        logger.error(f"Git pull failed for {repo_cfg.name}:{repo_cfg.branch}")
        push_github_commit_status(status)
        send_notification(status, CICD_DISCORD_WEBHOOK_URL)
        return

    # Docker Compose
    status.docker_execution_result = run_command(
        ["docker", "compose", "up", "--build", "-d"], repo_cfg.path
    )

    if not status.docker_execution_result.success:
        logger.error(f"Docker build/up failed for {repo_cfg.name}:{repo_cfg.branch}")
        
        if repo_cfg.enable_rollback and backup_branch:
            rollback_success = perform_rollback(repo_cfg, backup_branch)
            if rollback_success:
                status.commit_msg += " [ROLLED BACK DUE TO DOCKER FAILURE]"
        
        push_github_commit_status(status)
        send_notification(status, CICD_DISCORD_WEBHOOK_URL)
        return

    if repo_cfg.containers_to_force_recreate:
        command = ["docker", "compose", "up", "--build", "-d", "--force-recreate", "--no-deps"]
        command.extend(repo_cfg.containers_to_force_recreate)
        status.docker_force_execution_result = run_command(command, repo_cfg.path)

    if backup_branch:
        subprocess.run(["git", "branch", "-D", backup_branch], cwd=repo_cfg.path, capture_output=True)

    logger.error(f"deployment complete for {repo_cfg.name}:{repo_cfg.branch}")
    push_github_commit_status(status)
    send_notification(status, CICD_DISCORD_WEBHOOK_URL)
    get_docker_images_disk_usage_bytes()


def should_skip_deployment(files_changed: List[str], ignore_patterns: List[str]) -> bool:
    """
    Returns True if ALL changed files match the ignore patterns.
    """
    if not ignore_patterns:
        return False
    
    if not files_changed:
        # if we can't see the files, deploy anyway
        return False

    for file in files_changed:
        # check if the current file matches any of the ignore patterns
        is_ignored = any(fnmatch.fnmatch(file, pattern) for pattern in ignore_patterns)
        
        # if any file is outside the ignore pattern, we should deploy
        if not is_ignored:
            return False
            
    return True


app = FastAPI()
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

REPO_MAP: Dict[Tuple[str, str], RepoConfig] = {}

# dis one loads the config.yml file
# turns it into a dictionary
# result is the dictionary
try:
    with open(args.config) as f:
        data = yaml.safe_load(f)
        raw_repos = data.get("repos", [])
        SMEE2_URL = data.get("smee2_url")
        SMEE2_API_KEY = data.get("smee2_api_key")
        CICD_DISCORD_WEBHOOK_URL = data.get("cicd_discord_webhook_url")
        GITHUB_TOKEN = data.get("github_token")
        PASTEBIN_API_KEY = data.get("cleezy_token")
        PUSHGATEWAY_URL = data.get("pushgateway_url")
        for r in raw_repos:
            # make a new entry into the result dictionary
            # the key is a tuple of the repo name and branch
            # the value is a RepoToWatch object
            unknown_fields = validate_config(r)
            if unknown_fields: # removes any extra fields not in RepoConfig
                for f in unknown_fields:
                    r.pop(f)
            cfg = RepoConfig(**r)
            REPO_MAP[(cfg.name, cfg.branch)] = cfg
        logger.info(f'loaded {len(raw_repos)} repo(s) from config {args.config}')
except Exception:
    logger.exception(f"Failed to load config at path {args.config}")

def deployment_worker(target: RepoConfig, is_dev: bool):
    key = (target.name, target.branch)
    q = REPO_QUEUES[key]

    try:
        # hai welcome to the deployment house
        while True:
            # kicking a guy outta line rn brb
            payload = q.get()
            
            # debounce,: skip the stale entriesand grab the newest one.
            # this disqualifies the older waiting deployments
            while not q.empty():
                logger.info(f"Discarding outdated request for {target.name} (newer one waiting)")
                payload = q.get()

            try:
                handle_deploy(target, payload, is_dev)
            except Exception:
                logger.exception(f"Worker failed during deploy of {target.name}")
            finally:
                q.task_done()

            with THREAD_MANAGER_LOCK:
                if q.empty():
                    ACTIVE_WORKERS.remove(key)
                    logger.info(f"Worker for {target.name} exiting (queue empty)")
                    return
    except Exception:
        logger.exception(f"Fatal error in worker thread for {target.name}")
        with THREAD_MANAGER_LOCK:
            ACTIVE_WORKERS.discard(key)


def trigger_deployment(target: RepoConfig, data: dict, is_dev: bool):
    key = (target.name, target.branch)
    
    with THREAD_MANAGER_LOCK:
        # Create queue if it doesn't exist
        if key not in REPO_QUEUES:
            REPO_QUEUES[key] = queue.Queue()
        
        # Add the work to the queue
        REPO_QUEUES[key].put(data)
        
        # If no worker is running for this repo, start one
        if key not in ACTIVE_WORKERS:
            ACTIVE_WORKERS.add(key)
            t = threading.Thread(
                target=deployment_worker, 
                args=(target, is_dev), 
                daemon=True,
                name=f"Worker-{target.name}"
            )
            t.start()
            logger.info(f"Started new worker thread for {target.name}")

def handle_workflow_run_event(payload: dict, target: RepoConfig):
    if not target.actions_need_to_pass:
        return {"status": "ignored", "reason": f"actions_need_to_pass is not set to True for {target.name}:{target.branch}"}

    action = payload.get("action")
    run_data = payload.get("workflow_run", {})
    conclusion = run_data.get("conclusion")
    
    logger.info(f"Workflow {run_data.get('name')} for {target.name} is {action} ({conclusion})")

    if action == "completed" and conclusion == "success":
        logger.info(f"Workflow passed! Triggering deployment for {target.name}:{target.branch}")
        
        push_payload = {
            "head_commit": {
                "id": run_data.get("head_sha"),
                "message": run_data.get("display_title"),
                "author": {"username": run_data.get("triggering_actor", {}).get("login", "Github Actions")}
            }
        }
        
        trigger_deployment(target, payload, args.development)
        return {"status": "accepted", "reason": "workflow success triggered deploy"}

    return {"status": "ignored", "reason": f"Workflow state {action}/{conclusion} does not trigger deploy"}


def handle_push_event(data: dict, target: RepoConfig):
    """Handles logic specific to GitHub 'push' events."""
    if target.actions_need_to_pass:
        return {"status": "ignored", "reason": "actions_need_to_pass is set to True, waiting for workflow_run success"}

    repo_name = target.name
    branch = data.get("ref", "").split("/")[-1]

    if not args.development:
        current_branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=target.path,
            capture_output=True,
            text=True,
        )
        current_branch = current_branch_result.stdout.strip()

        if current_branch != branch:
            logger.warning(f"Branch mismatch for {repo_name}")
            push_skipped_update_as_discord_embed_mismatched_branch(target, branch, current_branch, CICD_DISCORD_WEBHOOK_URL)
            return {"status": "skipped", "reason": "branch mismatch"}

    head_commit = data.get("head_commit") or {}
    files_changed = (
        head_commit.get("added", []) + 
        head_commit.get("modified", []) + 
        head_commit.get("removed", [])
    )

    if should_skip_deployment(files_changed, target.docker_ignore):
        logger.info(f"Skipping deployment for {repo_name}: All files match docker_ignore.")
        push_skipped_update_as_discord_embed_docker_ignore(target, files_changed, CICD_DISCORD_WEBHOOK_URL)
        return {"status": "skipped", "reason": "all changed files ignored"}

    logger.info(f"Accepted push for {repo_name}:{branch}")
    trigger_deployment(target, data, args.development)
    return {"status": "accepted"}

def create_backup_branch(repo_cfg: RepoConfig) -> Optional[str]:
    """Creates a temporary local branch to save the current state before pulling."""
    timestamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_name = f"backup-{timestamp}-{repo_cfg.branch}"
    try:
        subprocess.run(["git", "checkout", repo_cfg.branch], cwd=repo_cfg.path, check=True, capture_output=True)
        subprocess.run(["git", "branch", backup_name], cwd=repo_cfg.path, check=True, capture_output=True)
        logger.info(f"Created backup snapshot: {backup_name}")
        return backup_name
    except Exception:
        logger.exception(f"Failed to create backup for {repo_cfg.name}:{repo_cfg.branch}")
        return None

def perform_rollback(repo_cfg: RepoConfig, backup_name: str):
    """Resets the branch to the backup and restarts the containers."""
    try:
        logger.warning(f"Rolling back {repo_cfg.name} to {backup_name}")
        # reset the local branch to exactly what was in the backup
        subprocess.run(["git", "reset", "--hard", backup_name], cwd=repo_cfg.path, check=True)
        # restart docker with the old (working) code
        subprocess.run(["docker", "compose", "up", "--build", "-d"], cwd=repo_cfg.path, check=True)
        return True
    except Exception:
        logger.exception(f"Rollback failed for {repo_cfg.name}:{repo_cfg.branch}")
        return False
    finally:
        # delete the backup branch after reset
        subprocess.run(["git", "branch", "-D", backup_name], cwd=repo_cfg.path, capture_output=True)


@app.get("/metrics")
def get_metrics():
    return Response(media_type="text/plain", content=generate_latest())


@app.get("/")
def health():
    return {"status": "ok", "dev_mode": args.development}


def smee_listen():
    if not SMEE2_URL:
        logger.info(f'not listening to any github traffic because smee2_url is empty in {args.config}')
        return Smee2ListenResult.SOCKET_COULDNT_CONNECT
    
    result = Smee2ListenResult.NOTHING
    try:
        # 1. Establish a synchronous connection
        ws = websocket.create_connection(SMEE2_URL, header={"X-API-Key": SMEE2_API_KEY})
        logger.info(f"Connected to smee at {SMEE2_URL}")
        
        # 2. Replace 'async for' with a blocking while loop
        while True:
            message = ws.recv()
            MetricsHandler.last_smee_request_timestamp.set(time.time())
            MetricsHandler.push(PUSHGATEWAY_URL)

            data = json.loads(message)
            # we used to get it like
            # event = request.headers.get("X-GitHub-Event")
            event = None
            repositiory = data.get("repository", {})


            repo_name = repositiory.get("name")
            branch = None
            
            if data.get("pusher"):
                branch = data.get("ref", "").split("/")[-1]
                event = "push"
            elif data.get("workflow_run"):
                branch = data.get("workflow_run", {}).get("head_branch")
                event = "workflow_run"

            target = REPO_MAP.get((repo_name, branch))

            if not target:
                logger.debug(f"No configuration found for {repo_name}:{branch}")
                continue

            if event == "push":
                handle_push_event(data, target)
            elif event == "workflow_run":
                handle_workflow_run_event(data, target)
                
    except websocket.WebSocketConnectionClosedException:
        logger.warning("Smee WebSocket connection closed by the server.")
        result = Smee2ListenResult.SOCKET_CLOSED
    except Exception as e:
        logger.exception(f"could not connect to smee2 url {SMEE2_URL}")
        result = Smee2ListenResult.SOCKET_COULDNT_CONNECT
    finally:
        if 'ws' in locals():
            ws.close()
    return result


if __name__ == "server":
    MetricsHandler.init()
    get_docker_images_disk_usage_bytes()
    while True:
        result = smee_listen()
        if result == Smee2ListenResult.SOCKET_COULDNT_CONNECT:
            break
        logger.warning('attempting to connect to socket again')
        time.sleep(5)


if __name__ == "__main__":
    uvicorn.run("server:app", port=args.port, reload=True)
