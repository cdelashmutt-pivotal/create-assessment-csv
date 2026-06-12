"""
GitHub API helpers for the assessment CSV generator.

Authentication: Personal Access Token (classic or fine-grained).
Required scopes: repo (or read:org for org repos, read:user for user repos).

For GitHub Enterprise Server, pass either the web URL or the API URL:
    e.g. https://github.example.com  (or https://github.example.com/api/v3)
"""

import re
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_BASE_URL = "https://api.github.com"
_USER_AGENT = "repo-assessment-csv/1.0"


def _normalize_base_url(url: str) -> str:
    """Convert a user-supplied GitHub URL to the correct API base URL.

    Handles the common mistake of passing the web URL instead of the API URL:
      https://github.com              → https://api.github.com
      https://github.example.com      → https://github.example.com/api/v3
      https://github.example.com/api/v3 → unchanged
    """
    url = url.rstrip("/")
    parsed = urlparse(url)
    host = parsed.hostname or ""

    if host == "github.com":
        return "https://api.github.com"
    if host == "api.github.com":
        return url
    # Self-hosted GHES: ensure /api/v3 path
    if not parsed.path.rstrip("/").endswith("/api/v3"):
        return f"{parsed.scheme}://{parsed.netloc}/api/v3"
    return url


def _session(auth: dict) -> requests.Session:
    """Return a Session with token auth, required headers, and retry logic."""
    sess = requests.Session()
    sess.headers.update({
        "Authorization": f"Bearer {auth['token']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": _USER_AGENT,
    })
    retry = Retry(total=3, backoff_factor=0.5,
                  status_forcelist=[500, 502, 503, 504],
                  allowed_methods=["GET"])
    sess.mount("https://", HTTPAdapter(max_retries=retry))
    return sess


def _paginate(url: str, auth: dict, params: dict = None):
    """Yield every item from a GitHub paginated endpoint (Link header)."""
    sess = _session(auth)
    next_url = url
    first = True
    while next_url:
        resp = sess.get(next_url, params=params if first else None, timeout=30)
        resp.raise_for_status()
        first = False
        data = resp.json()
        yield from (data if isinstance(data, list) else data.get("items", []))
        next_url = None
        for part in resp.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                m = re.search(r"<([^>]+)>", part.strip())
                if m:
                    next_url = m.group(1)
                break


def _strip_userinfo(url: str) -> str:
    return re.sub(r"(https?://)([^@]+@)", r"\1", url)


def _base_url(auth: dict) -> str:
    return _normalize_base_url(auth["base_url"])


def _get_user_login(auth: dict) -> str:
    base_url = _base_url(auth)
    sess = _session(auth)
    resp = sess.get(f"{base_url}/user", timeout=30)
    resp.raise_for_status()
    return resp.json()["login"]


def get_workspaces(auth: dict) -> list[dict]:
    """Return the authenticated user's personal account and all their organizations."""
    base_url = _base_url(auth)
    sess = _session(auth)

    resp = sess.get(f"{base_url}/user", timeout=30)
    resp.raise_for_status()
    user = resp.json()

    workspaces = [{"slug": user["login"], "name": user["login"]}]
    for org in _paginate(f"{base_url}/user/orgs", auth, {"per_page": 100}):
        workspaces.append({"slug": org["login"], "name": org["login"]})

    return workspaces


def get_repos(workspace: str, auth: dict) -> list[dict]:
    """Return all repos for a GitHub organization or the authenticated user's personal account."""
    base_url = _base_url(auth)
    user_login = _get_user_login(auth)

    if workspace == user_login:
        url = f"{base_url}/user/repos"
        params = {"per_page": 100, "type": "owner"}
    else:
        url = f"{base_url}/orgs/{workspace}/repos"
        params = {"per_page": 100, "type": "all"}

    return _normalize(list(_paginate(url, auth, params)), workspace)


def _normalize(repos: list[dict], workspace: str) -> list[dict]:
    return [
        {
            "workspace": workspace,
            "project_key": workspace,
            "project_name": workspace,
            "repo_name": r["name"],
            "slug": r["name"],
            "clone_url": _strip_userinfo(r["clone_url"]),
            "branch": r.get("default_branch") or "",
        }
        for r in repos
    ]


def list_branches(workspace: str, slug: str, auth: dict, **_) -> list[str]:
    """Return all branch names for a GitHub repository."""
    base_url = _base_url(auth)
    url = f"{base_url}/repos/{workspace}/{slug}/branches"
    return [b["name"] for b in _paginate(url, auth, {"per_page": 100})]


def fetch_repos_for_workspaces(workspace_slugs: list[str], auth: dict) -> list[dict]:
    """Fetch all repos across the given GitHub workspaces (organizations / personal account)."""
    base_url = _base_url(auth)
    user_login = _get_user_login(auth)
    repos = []
    for ws in workspace_slugs:
        try:
            if ws == user_login:
                url = f"{base_url}/user/repos"
                params = {"per_page": 100, "type": "owner"}
            else:
                url = f"{base_url}/orgs/{ws}/repos"
                params = {"per_page": 100, "type": "all"}
            repos.extend(_normalize(list(_paginate(url, auth, params)), ws))
        except requests.HTTPError as exc:
            print(f"WARNING: Could not fetch repos for '{ws}': {exc}")
    return repos
