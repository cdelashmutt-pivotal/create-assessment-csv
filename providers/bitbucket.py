"""
Bitbucket Cloud API helpers for the assessment CSV generator.

All public functions accept a ``requests.auth.HTTPBasicAuth`` instance.
The canonical authentication method is Bitbucket username + API Token.

To create an API Token with the required scopes:
  1. Click your profile picture in Bitbucket → Security
  2. Under "API tokens", select "Create API Token with Scopes"
  3. Choose the "BitBucket" app and enable these scopes:
       read:account
       read:workspace:bitbucket
       read:project:bitbucket
       read:repository:bitbucket
"""

import requests
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth
from urllib3.util.retry import Retry

BASE_URL = "https://api.bitbucket.org/2.0"
_USER_AGENT = "repo-assessment-csv/1.0"


def _session(auth: HTTPBasicAuth) -> requests.Session:
    """Return a Session with auth, User-Agent, and retry logic."""
    session = requests.Session()
    session.auth = auth
    session.headers.update({"User-Agent": _USER_AGENT})
    retry = Retry(total=3, backoff_factor=0.5,
                  status_forcelist=[500, 502, 503, 504],
                  allowed_methods=["GET"])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session

CSV_HEADER = [
    "Repository Url",
    "Branch",
    "Subfolder",
    "App Name",
    "Business Criticality",
    "Business App",
    "Business App Technical Owner",
    "Business App Business Owner",
    "Cost",
    "Program",
    "Investment Status",
]


def paginate(url: str, auth: HTTPBasicAuth, params: dict = None):
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


def get_workspaces(auth: HTTPBasicAuth) -> list[dict]:
    """Return workspace objects the authenticated user belongs to."""
    return [m["workspace"] for m in paginate(f"{BASE_URL}/user/workspaces", auth)]


def get_repos(workspace: str, auth: HTTPBasicAuth) -> list[dict]:
    """Return all repos in a workspace."""
    return list(paginate(
        f"{BASE_URL}/repositories/{workspace}",
        auth,
        {"pagelen": 100},
    ))


def clone_url(repo: dict) -> str:
    """Extract the HTTPS clone URL from a repository object."""
    for link in repo.get("links", {}).get("clone", []):
        if link.get("name") == "https":
            return link["href"]
    workspace = repo["workspace"]["slug"]
    slug = repo["slug"]
    return f"https://bitbucket.org/{workspace}/{slug}.git"


def default_branch(repo: dict) -> str:
    """Return the name of the repository's default/main branch."""
    mb = repo.get("mainbranch")
    return mb["name"] if mb and mb.get("name") else ""


def fetch_repos_for_workspaces(workspace_slugs: list[str], auth: HTTPBasicAuth) -> list[dict]:
    """
    Fetch all repos across the given workspaces.

    Returns a flat list of dicts with keys:
        workspace, project_key, project_name, repo_name, slug, clone_url, branch

    Workspaces or projects that return an HTTP error are skipped with a warning
    printed to stdout.
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
