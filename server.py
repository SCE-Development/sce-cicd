import json
import logging
import os
import subprocess
import threading
from pathlib import Path

import uvicorn
import yaml
from fastapi import FastAPI, Request
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

with open("config.yml") as f:
    config = yaml.safe_load(f)

BASE_PATH = Path(config["base_path"])
WATCHED_REPOS = {(repo["name"], repo["branch"]) for repo in config["repos"]}

def update_repo(repo_name: str, branch: str):
    logger.info(f"updating {repo_name} to {branch}")
    try:
        repo_path = BASE_PATH / repo_name
        logger.info(f"Changing to directory: {repo_path}")
        
        os.chdir(repo_path)
        
        git_result = subprocess.run(['git', 'pull', 'origin', branch])
        logger.info(f"Git pull output: {git_result.stdout}")
        if git_result.stderr:
            logger.info(f"Git pull status: {git_result.stderr}")
        
        docker_result = subprocess.run(['docker-compose', 'up', '--build', '-d'])
        logger.info(f"Docker compose output: {docker_result.stdout}")
        if docker_result.returncode != 0:
            logger.error(f"Docker compose failed with status: {docker_result.returncode}")
            
    except Exception as e:
        logger.error(f"Error updating repository: {str(e)}")
        logger.error(f"Current working directory: {os.getcwd()}")

@app.post("/webhook")
async def github_webhook(request: Request):
    payload_body = await request.body()
    payload = json.loads(payload_body)
    print(payload)
    
    # check if this is a push event
    if request.headers.get("X-GitHub-Event") == "push":
        ref = payload.get("ref")
        branch = ref.split("/")[-1]
        repo_name = payload.get("repository").get("name")
        
        if (repo_name, branch) in WATCHED_REPOS:
            logger.info(f"Push to {branch} detected for {repo_name}")
            # update the repo
            thread = threading.Thread(target=update_repo, args=(repo_name, branch))
            thread.start()
    
    return {"status": "webhook received"}

@app.get("/")
def read_root():
    return {"message": "SCE CICD Server"}

def start_smee():
    try:
        result = subprocess.run(['tmux', 'has-session', '-t', 'smee'], capture_output=True)
        if result.returncode != 0:
            subprocess.run(['tmux', 'new-session', '-d', '-s', 'smee'])
        
        # sends the smee command to the tmux session named smee
        smee_cmd = f"smee --url {os.getenv('SMEE_URL')} --target http://127.0.0.1:3000/webhook"
        subprocess.run(['tmux', 'send-keys', '-t', 'smee', smee_cmd, 'Enter'])
        logger.info("Smee started in tmux session 'smee'")
    except Exception as e:
        logger.error(f"Error starting smee: {e}")

if __name__ == "__main__":
    start_smee()
    uvicorn.run("server:app", port=3000, reload=True)
