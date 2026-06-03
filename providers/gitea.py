"""
Gitea / Forgejo API helpers for the assessment CSV generator.

Authentication: Personal Access Token (or application token).
Required scopes: read:organization, read:repository, read:user.

base_url is required and must point to your Gitea/Forgejo instance:
    e.g. https://gitea.example.com
"""

import re

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_BASE_URL = ""  # No cloud default — instance URL is required
_USER_AGENT = "repo-assessment-csv/1.0"
_PAGE_LIMIT = 50


def _session(auth: dict) -> requests.Session:
    """Return a Session with token auth and retry logic."""
    sess = requests.Session()
    sess.headers.update({
        "Authorization": f"token {auth['token']}",
        "User-Agent": _USER_AGENT,
    })
    retry = Retry(total=3, backoff_factor=0.5,
                  status_forcelist=[500, 502, 503, 504],
                  allowed_methods=["GET"])
    sess.mount("https://", HTTPAdapter(max_retries=retry))
    sess.mount("http://", HTTPAdapter(max_retries=retry))
    return sess


def _api(auth: dict) -> str:
    return auth["base_url"].rstrip("/") + "/api/v1"


def _paginate(url: str, auth: dict, params: dict = None):
    """Yield every item from a Gitea paginated endpoint."""
    sess = _session(auth)
    p = dict(params or {})
    p.setdefault("limit", _PAGE_LIMIT)
    page = 1
    while True:
        p["page"] = page
        resp = sess.get(url, params=p, timeout=30)
        resp.raise_for_status()
        items = resp.json()
        if not items:
            break
        yield from items
        if len(items) < p["limit"]:
            break
        page += 1


def _strip_userinfo(url: str) -> str:
    return re.sub(r"(https?://)([^@]+@)", r"\1", url)


def _get_username(auth: dict) -> str:
    api = _api(auth)
    sess = _session(auth)
    resp = sess.get(f"{api}/user", timeout=30)
    resp.raise_for_status()
    return resp.json()["login"]


def get_workspaces(auth: dict) -> list[dict]:
    """Return the authenticated user's organizations and personal account."""
    api = _api(auth)
    username = _get_username(auth)

    workspaces = [{"slug": username, "name": username}]
    for org in _paginate(f"{api}/user/orgs", auth):
        workspaces.append({"slug": org["username"], "name": org["full_name"] or org["username"]})

    return workspaces


def get_repos(workspace: str, auth: dict) -> list[dict]:
    """Return all repos for a Gitea organization or the authenticated user's personal account."""
    api = _api(auth)
    username = _get_username(auth)

    if workspace == username:
        url = f"{api}/user/repos"
    else:
        url = f"{api}/orgs/{workspace}/repos"

    return _normalize(list(_paginate(url, auth)), workspace)


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


def fetch_repos_for_workspaces(workspace_slugs: list[str], auth: dict) -> list[dict]:
    """Fetch all repos across the given Gitea workspaces (organizations / personal account)."""
    api = _api(auth)
    username = _get_username(auth)
    repos = []
    for ws in workspace_slugs:
        try:
            url = f"{api}/user/repos" if ws == username else f"{api}/orgs/{ws}/repos"
            repos.extend(_normalize(list(_paginate(url, auth)), ws))
        except requests.HTTPError as exc:
            print(f"WARNING: Could not fetch repos for '{ws}': {exc}")
    return repos
