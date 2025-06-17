import json
import logging
import os
import subprocess
import threading

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

with open("config.yaml") as f:
    config = yaml.safe_load(f)

BASE_PATH = config["base_path"]
WATCHED_REPOS = {(repo["name"], repo["branch"]) for repo in config["repos"]}

def update_repo(repo_name: str, branch: str):
    logger.info(f"updating {repo_name} to {branch}")
    try:
        repo_path = os.path.join(BASE_PATH, repo_name)
        logger.info(f"Changing to directory: {repo_path}")
        
        os.chdir(repo_path)
        
        git_result = subprocess.run(['git', 'pull'], capture_output=True, text=True)
        logger.info(f"Git pull output: {git_result.stdout}")
        if git_result.stderr:
            logger.error(f"Git pull error: {git_result.stderr}")
        
        docker_result = subprocess.run(['docker-compose', 'up', '--build', '-d'], capture_output=True, text=True)
        logger.info(f"Docker compose output: {docker_result.stdout}")
        if docker_result.stderr:
            logger.error(f"Docker compose error: {docker_result.stderr}")
            
    except Exception as e:
        logger.error(f"Error updating repository: {str(e)}")
        logger.error(f"Current working directory: {os.getcwd()}")

# smee --url https://smee.io/PwN1nwSMs3vL1Vr5 --target http://127.0.0.1:3000/webhook

@app.post("/webhook")
async def github_webhook(request: Request):
    payload_body = await request.body()
    payload = json.loads(payload_body)
    
    # check if this is a push event
    if request.headers.get("X-GitHub-Event") == "push":
        ref = payload.get("ref")
        branch = ref.split("/")[-1]
        repo_name = payload.get("repository").get("name")
        
        # O(1) lookup lol
        if (repo_name, branch) in WATCHED_REPOS:
            logger.info(f"Push to {branch} detected for {repo_name}")
            # update the repo
            thread = threading.Thread(target=update_repo, args=(repo_name, branch))
            thread.start()
    
    return {"status": "webhook received"}

@app.get("/")
def read_root():
    return {"message": "SCE CICD Server"}

if __name__ == "__main__":
    uvicorn.run(app, port=3000)
