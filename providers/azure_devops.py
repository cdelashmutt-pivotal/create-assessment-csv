"""
Azure DevOps API helpers for the assessment CSV generator.

Authentication: Personal Access Token (PAT).
Required scopes: Code (Read), Project and Team (Read).

For Azure DevOps Services (cloud), base_url should be:
    https://dev.azure.com

For Azure DevOps Server (on-premises), set base_url to your collection URL:
    e.g. https://ado.example.com/tfs/MyCollection

Organization discovery uses the Azure DevOps Services Accounts API and only
works with the cloud URL. For on-premises instances, a single virtual
organization is inferred from the base_url path.
"""

import base64
import re

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_BASE_URL = "https://dev.azure.com"
_VSSPS_BASE = "https://app.vssps.visualstudio.com"
_API_VERSION = "7.1"
_USER_AGENT = "repo-assessment-csv/1.0"


def _session(auth: dict) -> requests.Session:
    """Return a Session using PAT Basic auth and retry logic."""
    sess = requests.Session()
    # Azure DevOps PAT auth: Basic base64(":token")
    encoded = base64.b64encode(f":{auth['token']}".encode()).decode()
    sess.headers.update({
        "Authorization": f"Basic {encoded}",
        "User-Agent": _USER_AGENT,
    })
    retry = Retry(total=3, backoff_factor=0.5,
                  status_forcelist=[500, 502, 503, 504],
                  allowed_methods=["GET"])
    sess.mount("https://", HTTPAdapter(max_retries=retry))
    sess.mount("http://", HTTPAdapter(max_retries=retry))
    return sess


def _is_cloud(auth: dict) -> bool:
    return "dev.azure.com" in auth["base_url"]


def _paginate(url: str, auth: dict, params: dict = None):
    """Yield every item from an Azure DevOps paginated endpoint (continuationToken)."""
    sess = _session(auth)
    p = dict(params or {})
    p["api-version"] = _API_VERSION
    while True:
        resp = sess.get(url, params=p, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        yield from data.get("value", [])
        token = resp.headers.get("x-ms-continuationtoken")
        if not token:
            break
        p["continuationToken"] = token


def _strip_userinfo(url: str) -> str:
    return re.sub(r"(https?://)([^@]+@)", r"\1", url)


def _strip_refs_heads(branch: str) -> str:
    """Convert 'refs/heads/main' → 'main'."""
    if branch and branch.startswith("refs/heads/"):
        return branch[len("refs/heads/"):]
    return branch or ""


def get_workspaces(auth: dict) -> list[dict]:
    """
    Return Azure DevOps organizations the authenticated user belongs to.

    For cloud (dev.azure.com), organizations are discovered via the Accounts API.
    For on-premises, a single virtual organization is derived from the base_url.
    """
    if _is_cloud(auth):
        sess = _session(auth)
        # Get public alias from user profile
        resp = sess.get(
            f"{_VSSPS_BASE}/_apis/profile/profiles/me",
            params={"api-version": _API_VERSION},
            timeout=30,
        )
        resp.raise_for_status()
        alias = resp.json().get("publicAlias")

        resp2 = sess.get(
            f"{_VSSPS_BASE}/_apis/accounts",
            params={"memberId": alias, "api-version": _API_VERSION},
            timeout=30,
        )
        resp2.raise_for_status()
        accounts = resp2.json().get("value", [])
        return [{"slug": a["accountName"], "name": a["accountName"]} for a in accounts]
    else:
        # On-premises: derive collection name from the last non-empty path segment
        parts = [p for p in auth["base_url"].rstrip("/").split("/") if p]
        # Strip scheme component (e.g. "https:")
        parts = [p for p in parts if not p.endswith(":")]
        collection = parts[-1] if len(parts) > 1 else "DefaultCollection"
        return [{"slug": collection, "name": collection}]


def _projects_url(auth: dict, org: str) -> str:
    base = auth["base_url"].rstrip("/")
    if _is_cloud(auth):
        return f"{base}/{org}/_apis/projects"
    else:
        return f"{base}/_apis/projects"


def _repos_url(auth: dict, org: str, project_name: str) -> str:
    base = auth["base_url"].rstrip("/")
    if _is_cloud(auth):
        return f"{base}/{org}/{project_name}/_apis/git/repositories"
    else:
        return f"{base}/{project_name}/_apis/git/repositories"


def get_repos(workspace: str, auth: dict) -> list[dict]:
    """Return all Git repos across all projects within an Azure DevOps organization."""
    repos = []
    for project in _paginate(_projects_url(auth, workspace), auth):
        project_name = project["name"]
        project_id = project["id"]
        try:
            for repo in _paginate(_repos_url(auth, workspace, project_name), auth):
                repos.append({
                    "workspace": workspace,
                    "project_key": project_id,
                    "project_name": project_name,
                    "repo_name": repo["name"],
                    "slug": repo["name"],
                    "clone_url": _strip_userinfo(repo.get("remoteUrl", "")),
                    "branch": _strip_refs_heads(repo.get("defaultBranch", "")),
                })
        except requests.HTTPError as exc:
            print(f"WARNING: Could not fetch repos for project '{project_name}': {exc}")
    return repos


def fetch_repos_for_workspaces(workspace_slugs: list[str], auth: dict) -> list[dict]:
    """Fetch all repos across the given Azure DevOps organizations."""
    repos = []
    for ws in workspace_slugs:
        try:
            repos.extend(get_repos(ws, auth))
        except requests.HTTPError as exc:
            print(f"WARNING: Could not fetch repos for organization '{ws}': {exc}")
    return repos
