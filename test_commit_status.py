import os 
import subprocess 

from dotenv import load_dotenv 

from modules.commit_status_helpers import (
    CommitStatus, 
    push_commit_status,
)

def main(): 
    # load variables from .env
    load_dotenv() 

    # read github token from .env
    github_token = os.getenv("GITHUB_TOKEN")

    if github_token is None: 
        raise RuntimeError("GITHUB_TOKEN not found in .env")

    # get SHA of the latest commit 
    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"]
    ).decode().strip() 

    # create the commit status object 
    status = CommitStatus(
        state="success", 
        description="hello world", 
        context="sce-cicd"
    )

    # send the status to github 
    response = push_commit_status(
        owner="SCE-Development", 
        repo="sce-cicd", 
        sha=sha, 
        token=github_token, 
        status=status, 
    )

    print("Commit status successfully pushed!")
    print(response)

if __name__ == "__main__": 
    main() 