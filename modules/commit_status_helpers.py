from dataclasses import asdict, dataclass 
from typing import Literal 
import json 
import urllib.error 
import urllib.request

CommitState = Literal["error", "failure", "pending", "success"] 

@dataclass(frozen=True)
class CommitStatus: 
    state: CommitState
    description: str | None = None 
    context: str | None = None 
    target_url: str | None = None 

    # converts this dataclass into a dictionary that GitHub's API can accept, gets rid of any None values 
    def to_payload(self) -> dict[str, str]: 
        return {
            key: value 
            for key, value in asdict(self).items()
            if value is not None 
        }

# function that sends a commit status to GitHub 
def push_commit_status(
        *,
        owner: str, 
        repo: str, 
        sha: str, 
        token: str, 
        status: CommitStatus, 
        timeout_seconds: float = 15.0,

) -> dict: # function will return a dictionary 
    if not owner.strip(): 
        raise ValueError("owner cannot be empty")
    if not repo.strip(): 
        raise ValueError("repo cannot be empty")
    if not sha.strip(): 
        raise ValueError("sha cannot be empty")
    if not token.strip(): 
        raise ValueError("Github token cannot be empty")
    # build the GitHub API URL 
    url = (
        f"https://api.github.com/repos/"
        f"{owner.strip()}/{repo.strip()}/statuses/{sha.strip()}"
    )

    # create an HTTP POST request 
    request = urllib.request.Request(
        url = url, 
        data = json.dumps(status.to_payload()).encode("utf-8"), 
        headers = {
            "Authorization": f"Bearer {token.strip()}", 
            "Accept": "application/vnd.github+json", 
            "Content-Type": "application/json", 
            "User-Agent": "sce-cicd",
        }, 
        method = "POST", 
    )

    # try sending the request
    try: 
        with urllib.request.urlopen(
            request, 
            timeout = timeout_seconds, 
        ) as response: 
            response_body = response.read().decode("utf-8") 
            return json.loads(response_body)
        
    except urllib.error.HTTPError as error: 
        error_body = error.read().decode("utf-8", errors = "replace")
        raise RuntimeError(
            f"GitHub rejected the commit status request " 
            f"with HTTP {error.code}: {error_body}"
        ) from error 
    
    except urllib.error.URLError as error: 
        raise RuntimeError(
            f"Could not connect to GitHub: {error.reason}"
        ) from error 

