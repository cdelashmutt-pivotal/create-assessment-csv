#!/usr/bin/env python3
"""
Repository Assessment CSV Generator — CLI

Queries a Git provider API for all repositories visible to the provided
credentials, then writes a CSV in the format expected by the assessment
input template.

Supported providers: bitbucket (default), github, gitlab, azuredevops, gitea

Usage:
    python generate_assessment_csv.py                  # interactive prompts
    python generate_assessment_csv.py --provider github --token <PAT>
    python generate_assessment_csv.py --provider gitea --base-url https://gitea.example.com --token <tok>

For an interactive web UI, run the Flask app instead:
    flask run   (then open http://localhost:5000)
"""

import argparse
import csv
import getpass
import sys

import requests

from providers import CSV_HEADER_FIXED, PROVIDER_BASE_URLS, get_provider

# ---------------------------------------------------------------------------
# Configuration — edit these values before running (or use CLI flags)
# ---------------------------------------------------------------------------

# Default values written to every row
DEFAULT_BUSINESS_CRITICALITY = "High" # e.g. Critical, High, Medium, Low
DEFAULT_TECHNICAL_OWNER = "Sandeep"   # Free text — name, email, etc.
DEFAULT_BUSINESS_OWNER = ""           # Free text — name, email, etc.
DEFAULT_COST = "High"                 # High, Medium, Low

# ---------------------------------------------------------------------------
# Extra columns — appended after "Cost" in every row.
# Example:
#   EXTRA_COLUMNS = [
#       {"name": "Program",           "default": ""},
#       {"name": "Investment Status", "default": "Sustain"},
#   ]
# ---------------------------------------------------------------------------
EXTRA_COLUMNS = []

# Workspace / org / group slugs to export.
# Leave as [] to auto-discover all workspaces the user belongs to.
WORKSPACES = []   # e.g. ["my-workspace", "another-workspace"]

# Output file path
OUTPUT_FILE = "assessment_input.csv"

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

PROVIDER_AUTH_HINTS = {
    "bitbucket": (
        "Bitbucket API Token",
        "  Profile picture \u2192 Security \u2192 Create API Token with Scopes (BitBucket app)\n"
        "  Scopes: read:account, read:workspace:bitbucket, read:project:bitbucket, read:repository:bitbucket",
    ),
    "github": (
        "GitHub Personal Access Token",
        "  Settings \u2192 Developer settings \u2192 Personal access tokens\n"
        "  Scopes: repo (or read:org + read:user)",
    ),
    "gitlab": (
        "GitLab Personal Access Token",
        "  User Settings \u2192 Access Tokens\n"
        "  Scopes: read_api",
    ),
    "azuredevops": (
        "Azure DevOps Personal Access Token",
        "  User settings \u2192 Personal access tokens\n"
        "  Scopes: Code (Read), Project and Team (Read)",
    ),
    "gitea": (
        "Gitea / Forgejo API Token",
        "  Settings \u2192 Applications \u2192 Manage Access Tokens\n"
        "  Scopes: read:organization, read:repository, read:user",
    ),
}

WORKSPACE_LABELS = {
    "bitbucket":   "workspace",
    "github":      "organization",
    "gitlab":      "group",
    "azuredevops": "organization",
    "gitea":       "organization",
}


def parse_args():
    p = argparse.ArgumentParser(description="Generate a repository assessment CSV.")
    p.add_argument("--provider", default="bitbucket",
                   choices=["bitbucket", "github", "gitlab", "azuredevops", "gitea"],
                   help="Git provider (default: bitbucket)")
    p.add_argument("--base-url", default="",
                   help="API base URL (overrides provider default; required for Gitea)")
    p.add_argument("--username", default="",
                   help="Username (required for Bitbucket)")
    p.add_argument("--token", default="",
                   help="API / Personal Access Token (will prompt if not provided)")
    p.add_argument("--workspaces", default="", metavar="SLUGS",
                   help="Comma-separated workspace/org/group slugs (auto-discovers if omitted)")
    p.add_argument("--output", default=OUTPUT_FILE,
                   help=f"Output CSV file path (default: {OUTPUT_FILE})")
    return p.parse_args()


def main():
    args = parse_args()
    provider_name = args.provider

    try:
        mod = get_provider(provider_name)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    ws_label = WORKSPACE_LABELS.get(provider_name, "workspace")
    token_name, hint = PROVIDER_AUTH_HINTS.get(provider_name, ("API Token", ""))

    # --- Gather credentials interactively if not provided via flags ---
    if hint:
        print(f"{token_name} required.")
        print(hint)
        print()

    username = args.username
    if provider_name == "bitbucket" and not username:
        username = input("Bitbucket username: ").strip()
        if not username:
            print("ERROR: Username is required for Bitbucket.")
            sys.exit(1)

    base_url = args.base_url
    if not base_url:
        if provider_name == "gitea":
            base_url = input("Gitea/Forgejo instance URL: ").strip()
            if not base_url:
                print("ERROR: Instance URL is required for Gitea/Forgejo.")
                sys.exit(1)
        else:
            base_url = mod.DEFAULT_BASE_URL

    token = args.token
    if not token:
        token = getpass.getpass(f"{token_name}: ").strip()
    if not token:
        print(f"ERROR: {token_name} is required.")
        sys.exit(1)

    auth = {"token": token, "base_url": base_url}
    if provider_name == "bitbucket":
        auth["username"] = username

    # --- Workspace / org discovery ---
    workspace_slugs = [s.strip() for s in args.workspaces.split(",") if s.strip()] or WORKSPACES
    if not workspace_slugs:
        print(f"Discovering {ws_label}s…")
        try:
            workspace_slugs = [ws["slug"] for ws in mod.get_workspaces(auth)]
        except requests.HTTPError as exc:
            print(f"ERROR: Could not fetch {ws_label}s: {exc}")
            sys.exit(1)

    if not workspace_slugs:
        print(f"No {ws_label}s found for the provided credentials.")
        sys.exit(0)

    print(f"Processing {len(workspace_slugs)} {ws_label}(s): {', '.join(workspace_slugs)}")

    # --- Fetch repos ---
    try:
        repos = mod.fetch_repos_for_workspaces(workspace_slugs, auth)
    except requests.RequestException as exc:
        print(f"ERROR: Network error while fetching repositories: {exc}")
        sys.exit(1)

    # --- Write CSV ---
    output_file = args.output
    rows = [
        [
            r["clone_url"],
            r["branch"],
            "",
            r["repo_name"],
            DEFAULT_BUSINESS_CRITICALITY,
            r["project_name"],
            DEFAULT_TECHNICAL_OWNER,
            DEFAULT_BUSINESS_OWNER,
            DEFAULT_COST,
            *[c["default"] for c in EXTRA_COLUMNS],
        ]
        for r in repos
    ]

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER_FIXED + [c["name"] for c in EXTRA_COLUMNS])
        writer.writerows(rows)

    print(f"\nDone. Wrote {len(rows)} row(s) to {output_file}")


if __name__ == "__main__":
    main()
