"""
GitLab API helpers for the assessment CSV generator.

Authentication: Personal Access Token.
Required scopes: read_api (or api).

For self-managed GitLab, set base_url to your instance URL:
    e.g. https://gitlab.example.com
"""

import re

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_BASE_URL = "https://gitlab.com"
_USER_AGENT = "repo-assessment-csv/1.0"


def _session(auth: dict) -> requests.Session:
    """Return a Session with token auth and retry logic."""
    sess = requests.Session()
    sess.headers.update({
        "PRIVATE-TOKEN": auth["token"],
        "User-Agent": _USER_AGENT,
    })
    retry = Retry(total=3, backoff_factor=0.5,
                  status_forcelist=[500, 502, 503, 504],
                  allowed_methods=["GET"])
    sess.mount("https://", HTTPAdapter(max_retries=retry))
    return sess


def _api(auth: dict) -> str:
    return auth["base_url"].rstrip("/") + "/api/v4"


def _paginate(url: str, auth: dict, params: dict = None):
    """Yield every item from a GitLab paginated endpoint (Link header)."""
    sess = _session(auth)
    next_url = url
    first = True
    while next_url:
        resp = sess.get(next_url, params=params if first else None, timeout=30)
        resp.raise_for_status()
        first = False
        yield from resp.json()
        next_url = None
        for part in resp.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                m = re.search(r"<([^>]+)>", part.strip())
                if m:
                    next_url = m.group(1)
                break


def _strip_userinfo(url: str) -> str:
    return re.sub(r"(https?://)([^@]+@)", r"\1", url)


def _get_username(auth: dict) -> str:
    api = _api(auth)
    sess = _session(auth)
    resp = sess.get(f"{api}/user", timeout=30)
    resp.raise_for_status()
    return resp.json()["username"]


def get_workspaces(auth: dict) -> list[dict]:
    """Return the authenticated user's GitLab groups and personal namespace."""
    api = _api(auth)
    username = _get_username(auth)

    workspaces = [{"slug": username, "name": username}]
    for group in _paginate(f"{api}/groups", auth, {"per_page": 100, "min_access_level": 20, "top_level_only": "true"}):
        workspaces.append({"slug": group["full_path"], "name": group["name"]})

    return workspaces


def get_repos(workspace: str, auth: dict) -> list[dict]:
    """Return all projects (repos) for a GitLab group or personal namespace."""
    api = _api(auth)
    username = _get_username(auth)

    if workspace == username:
        # Personal namespace — fetch owned projects
        url = f"{api}/users/{username}/projects"
        params = {"per_page": 100, "owned": "true"}
    else:
        url = f"{api}/groups/{workspace}/projects"
        params = {"per_page": 100, "include_subgroups": "true"}

    return _normalize(list(_paginate(url, auth, params)))


def _normalize(projects: list[dict]) -> list[dict]:
    return [
        {
            "workspace": p.get("namespace", {}).get("full_path", ""),
            "project_key": str(p.get("namespace", {}).get("id", "")),
            "project_name": p.get("namespace", {}).get("name", ""),
            "repo_name": p["name"],
            "slug": p["path"],
            "clone_url": _strip_userinfo(p["http_url_to_repo"]),
            "branch": p.get("default_branch") or "",
        }
        for p in projects
    ]


def fetch_repos_for_workspaces(workspace_slugs: list[str], auth: dict) -> list[dict]:
    """Fetch all repos across the given GitLab workspaces (groups / personal namespace)."""
    api = _api(auth)
    username = _get_username(auth)
    repos = []
    for ws in workspace_slugs:
        try:
            if ws == username:
                url = f"{api}/users/{username}/projects"
                params = {"per_page": 100, "owned": "true"}
            else:
                url = f"{api}/groups/{ws}/projects"
                params = {"per_page": 100, "include_subgroups": "true"}
            repos.extend(_normalize(list(_paginate(url, auth, params))))
        except requests.HTTPError as exc:
            print(f"WARNING: Could not fetch repos for '{ws}': {exc}")
    return repos
