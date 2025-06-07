import json
import logging

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
    logger.info("hi ts is working")

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
            update_repo(repo_name, branch)
    
    return {"status": "yay"}

@app.get("/")
def read_root():
    return {"message": "SCE CICD Server"}

if __name__ == "__main__":
    uvicorn.run(app, port=8000)
