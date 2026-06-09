"""
Bitbucket Cloud API helpers for the assessment CSV generator.

Authentication: Bitbucket username + API Token.

To create an API Token with the required scopes:
  1. Click your profile picture in Bitbucket → Security
  2. Under "API tokens", select "Create API Token with Scopes"
  3. Choose the "BitBucket" app and enable these scopes:
       read:account
       read:workspace:bitbucket
       read:project:bitbucket
       read:repository:bitbucket

For self-hosted Bitbucket Server / Data Center, set base_url to your instance:
    e.g. https://bitbucket.example.com/rest/api/1.0
    (Note: Bitbucket Server uses a different REST API — cloud support only for now.)
"""

import re

import requests
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth
from urllib3.util.retry import Retry

DEFAULT_BASE_URL = "https://api.bitbucket.org/2.0"
_USER_AGENT = "repo-assessment-csv/1.0"


def _session(auth: dict) -> requests.Session:
    """Return a Session with Basic auth, User-Agent, and retry logic."""
    sess = requests.Session()
    sess.auth = HTTPBasicAuth(auth["username"], auth["token"])
    sess.headers.update({"User-Agent": _USER_AGENT})
    retry = Retry(total=3, backoff_factor=0.5,
                  status_forcelist=[500, 502, 503, 504],
                  allowed_methods=["GET"])
    sess.mount("https://", HTTPAdapter(max_retries=retry))
    return sess


def _base(auth: dict) -> str:
    return auth.get("base_url", DEFAULT_BASE_URL).rstrip("/")


def paginate(url: str, auth: dict, params: dict = None):
    """Yield every item from a paginated Bitbucket API endpoint."""
    sess = _session(auth)
    next_url = url
    while next_url:
        resp = sess.get(
            next_url,
            params=params if next_url == url else None,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        yield from data.get("values", [])
        next_url = data.get("next")


def get_workspaces(auth: dict) -> list[dict]:
    """Return workspace objects the authenticated user belongs to."""
    return [m["workspace"] for m in paginate(f"{_base(auth)}/user/workspaces", auth)]


def get_repos(workspace: str, auth: dict) -> list[dict]:
    """Return all repos in a workspace."""
    return list(paginate(
        f"{_base(auth)}/repositories/{workspace}",
        auth,
        {"pagelen": 100},
    ))


def _strip_userinfo(url: str) -> str:
    """Remove embedded username from a URL (e.g. https://user@host/... → https://host/...)."""
    return re.sub(r"(https?://)([^@]+@)", r"\1", url)


def clone_url(repo: dict) -> str:
    """Extract the HTTPS clone URL from a repository object."""
    for link in repo.get("links", {}).get("clone", []):
        if link.get("name") == "https":
            return _strip_userinfo(link["href"])
    workspace = repo["workspace"]["slug"]
    slug = repo["slug"]
    return f"https://bitbucket.org/{workspace}/{slug}.git"


def default_branch(repo: dict) -> str:
    """Return the name of the repository's default/main branch."""
    mb = repo.get("mainbranch")
    return mb["name"] if mb and mb.get("name") else ""


def list_branches(workspace: str, slug: str, auth: dict, **_) -> list[str]:
    """Return all branch names for a Bitbucket repository."""
    url = f"{_base(auth)}/repositories/{workspace}/{slug}/refs/branches"
    return [b["name"] for b in paginate(url, auth, {"pagelen": 100})]


def fetch_repos_for_workspaces(workspace_slugs: list[str], auth: dict) -> list[dict]:
    """
    Fetch all repos across the given workspaces.

    Returns a flat list of dicts with keys:
        workspace, project_key, project_name, repo_name, slug, clone_url, branch

    Workspaces that return an HTTP error are skipped with a warning.
    """
    repos = []
    for ws in workspace_slugs:
        try:
            ws_repos = get_repos(ws, auth)
        except requests.HTTPError as exc:
            print(f"WARNING: Could not fetch repos for workspace '{ws}': {exc}")
            continue
        for repo in ws_repos:
            project = repo.get("project", {})
            repos.append({
                "workspace": ws,
                "project_key": project.get("key", ""),
                "project_name": project.get("name", ""),
                "repo_name": repo["name"],
                "slug": repo["slug"],
                "clone_url": clone_url(repo),
                "branch": default_branch(repo),
            })
    return repos
