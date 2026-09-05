import dataclasses
import enum
from typing import List, Optional


@dataclasses.dataclass
class RepoConfig:
    name: str
    branch: str
    path: str
    # list of all the containers
    # makes sure theres a new list made for each repotowatch object
    containers_to_force_recreate: List[str] = dataclasses.field(default_factory=list)
    docker_ignore: List[str] = dataclasses.field(default_factory=list)
    actions_need_to_pass: bool = False
    enable_rollback: bool = False


@dataclasses.dataclass
class ExecutionResult:
    command: str
    exit_code: int = 1
    stdout: str = ""
    stderr: str = ""
    success: bool = False


@dataclasses.dataclass
class DeploymentStatus:
    repo: str
    branch: str
    commit_id: str = "commit_id not set"
    commit_msg: str = "commit_msg not set"
    author: str = "author not set"
    git_execution_result: Optional[ExecutionResult] = None
    docker_execution_result: Optional[ExecutionResult] = None
    docker_force_execution_result: Optional[ExecutionResult] = None
    is_dev: bool = False


class Smee2ListenResult(enum.Enum):
    NOTHING = 1
    SOCKET_CLOSED = 2
    SOCKET_COULDNT_CONNECT = 3
