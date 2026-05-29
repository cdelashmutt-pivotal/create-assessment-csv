#!/usr/bin/env python3
"""
Repository Assessment CSV Generator — Bitbucket Cloud (CLI)

Queries the Bitbucket Cloud API for all projects and repositories visible to
the provided credentials, then writes a CSV in the format expected by the
assessment input template.

Authentication: Bitbucket username + API Token.
  - Click your profile picture → Security → "Create API Token with Scopes"
  - Choose the "BitBucket" app and enable these scopes:
      read:account
      read:workspace:bitbucket
      read:project:bitbucket
      read:repository:bitbucket

Usage:
    python generate_assessment_csv.py

Output:
    assessment_input.csv  (in the current directory)

For an interactive web UI, run the Flask app instead:
    flask run   (then open http://localhost:5000)
"""

import csv
import getpass
import sys

import requests
from requests.auth import HTTPBasicAuth

from providers.bitbucket import CSV_HEADER_FIXED, fetch_repos_for_workspaces, get_workspaces

# ---------------------------------------------------------------------------
# Configuration — edit these values before running
# ---------------------------------------------------------------------------

# Default values written to every row
DEFAULT_BUSINESS_CRITICALITY = "High" # Can be anything but be consistent (e.g. critical, high, medium, low)
DEFAULT_TECHNICAL_OWNER = "Sandeep"   # Free text so it could be just names, email, etc.
DEFAULT_BUSINESS_OWNER = ""           # Free text so it could be just names, email, etc.
DEFAULT_COST = "High"                 # High, Medium, Low

# ---------------------------------------------------------------------------
# Extra columns — appended after "Cost" in every row.
# Add any number of custom columns here. Example:
#   EXTRA_COLUMNS = [
#       {"name": "Program",           "default": ""},
#       {"name": "Investment Status", "default": "Sustain"},
#   ]
# ---------------------------------------------------------------------------
EXTRA_COLUMNS = []

# Workspace slug(s) to export.
# Leave as an empty list [] to auto-discover all workspaces the user belongs to.
WORKSPACES = []                  # e.g. ["my-workspace", "another-workspace"]

# Output file path
OUTPUT_FILE = "assessment_input.csv"

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print("Bitbucket API Token required.")
    print("  Profile picture → Security → Create API Token with Scopes (BitBucket app)")
    print("  Scopes: read:account, read:workspace:bitbucket, read:project:bitbucket, read:repository:bitbucket")
    print()
    username = input("Bitbucket username: ").strip()
    api_token = getpass.getpass("API Token: ").strip()

    if not username or not api_token:
        print("ERROR: Username and API Token are required.")
        sys.exit(1)

    auth = HTTPBasicAuth(username, api_token)

    workspace_slugs = WORKSPACES
    if not workspace_slugs:
        try:
            workspace_slugs = [ws["slug"] for ws in get_workspaces(auth)]
        except requests.HTTPError as exc:
            print(f"ERROR: Could not fetch workspaces: {exc}")
            sys.exit(1)

    if not workspace_slugs:
        print("No workspaces found for the provided credentials.")
        sys.exit(0)

    print(f"Processing {len(workspace_slugs)} workspace(s): {', '.join(workspace_slugs)}")

    try:
        repos = fetch_repos_for_workspaces(workspace_slugs, auth)
    except requests.RequestException as exc:
        print(f"ERROR: Network error while fetching repositories: {exc}")
        sys.exit(1)

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

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER_FIXED + [c["name"] for c in EXTRA_COLUMNS])
        writer.writerows(rows)

    print(f"\nDone. Wrote {len(rows)} row(s) to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
