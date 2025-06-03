import logging
import subprocess
import threading
import time

import requests
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# in evan we trust
logging.basicConfig(
    format="%(asctime)s.%(msecs)03dZ %(levelname)s:%(name)s:%(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

OWNER = "SCE-Development"
POLL_INTERVAL = 60  # seconds

# define repos to monitor
REPOS = [
    {"name": "Clark", "branch": "cicd-testing"},
    # {"name": "SCE-repo", "branch": "blah"},
]

# swag one liner (repo_name, commit sha)
latest_commits = {repo["name"]: None for repo in REPOS}

def get_commit_sha(repo_name, branch):
    try:
        response = requests.get(
            f"https://api.github.com/repos/{OWNER}/{repo_name}/commits/{branch}",
            headers={"Accept": "application/vnd.github.v3+json"}
        )
        logger.info(f"sha: {response.json()['sha']}")
        return response.json()["sha"]
    except requests.RequestException as e:
        logger.error(f"error occurred for {repo_name}: {e}")
        return None

def poll_github():
    while True:
        for repo in REPOS:
            repo_name = repo["name"]
            branch = repo["branch"]
            
            new_sha = get_commit_sha(repo_name, branch)
            if new_sha is None:
                continue
                
            if latest_commits[repo_name] is not None and new_sha != latest_commits[repo_name]:
                logger.info(f"new commit detected in {repo_name} {branch}: {new_sha}")
                try:
                    # pull the latest changes
                    logger.info(f"Pulling latest changes for {repo_name}")
                    pull_result = subprocess.run(
                        ["git", "pull", "origin", branch],
                        cwd=repo_name,
                        check=True,
                        capture_output=True,
                        text=True
                    )
                    logger.info(f"Git pull successful for {repo_name}: {pull_result.stdout}")

                    # then rebuild and restart containers
                    logger.info(f"Rebuilding containers for {repo_name}")
                    subprocess.run(
                        ["docker", "compose", "up", "--build", "-d"],
                        cwd=repo_name,
                        check=True,
                        capture_output=True,
                        text=True
                    )
                    logger.info(f"Successfully rebuilt and restarted containers for {repo_name}")
                except subprocess.CalledProcessError as e:
                    logger.error(f"Failed to update or rebuild {repo_name}: {e.stderr}")
                except Exception as e:
                    logger.error(f"Unexpected error while updating or rebuilding {repo_name}: {str(e)}")
            
            latest_commits[repo_name] = new_sha
            
        time.sleep(POLL_INTERVAL)

@app.get("/")
def read_root():
    return {"message": "SCE CICD Server"}

@app.get("/latest-commit/{repo_name}")
def get_commit(repo_name):
    if repo_name not in latest_commits:
        return {"error": f"Repository {repo_name} not being monitored"}
    return {"sha": latest_commits[repo_name]}

@app.get("/latest-commits")
def get_all_commits():
    return latest_commits

if __name__ == "__main__":
    thread = threading.Thread(target=poll_github, daemon=True)
    thread.start()
    uvicorn.run(app, port=8000)
