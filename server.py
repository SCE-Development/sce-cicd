import json
import logging
import os
import subprocess
import threading

import uvicorn
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

def update_repo(repo_name: str, branch: str):
    logger.info(f"updating {repo_name} to {branch}")
    try:
        repo_path = os.path.join(os.path.expanduser('~'), repo_name)
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

@app.post("/webhook")
async def github_webhook(request: Request):
    payload_body = await request.body()
    payload = json.loads(payload_body)
    
    # check if this is a push event to cicd-testing branch
    if request.headers.get("X-GitHub-Event") == "push":
        ref = payload.get("ref")
        branch = ref.split("/")[-1]
        if branch == "cicd-testing":
            repo_name = payload.get("repository").get("name")
            logger.info(f"Push to {branch} detected for {repo_name}")
            # update the repo
            thread = threading.Thread(target=update_repo, args=(repo_name, branch))
            thread.start()
    
    return {"status": "webhook received"}

@app.get("/")
def read_root():
    return {"message": "SCE CICD Server"}

if __name__ == "__main__":
    uvicorn.run(app, port=8000)
