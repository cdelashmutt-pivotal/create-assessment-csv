#!/usr/bin/env python3
"""
Flask web app — Repository Assessment CSV Generator

Multi-step wizard:
  1. Select provider, enter credentials + configure CSV defaults
  2. Select workspaces / organizations / groups to include
  3. Review and toggle individual repos
  4. Download the generated CSV

Supported providers: Bitbucket, GitHub, GitLab, Azure DevOps, Gitea/Forgejo

Run locally:
    flask run          (then open http://localhost:5000)

Deploy to Cloud Foundry:
    cf push            (uses manifest.yml)
"""

import csv
import io
import json
import os
import secrets

import requests
from flask import (Flask, Response, flash, redirect, render_template,
                   request, session, url_for)

from providers import CSV_HEADER_FIXED, PROVIDER_BASE_URLS, WORKSPACE_LABELS, get_provider

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# ---------------------------------------------------------------------------
# Server-side defaults — override via CF environment variables
# ---------------------------------------------------------------------------
def _parse_extra_columns_env() -> list:
    try:
        cols = json.loads(os.environ.get("DEFAULT_EXTRA_COLUMNS", "[]"))
        if isinstance(cols, list):
            return [{"name": str(c.get("name", "")), "default": str(c.get("default", ""))}
                    for c in cols if isinstance(c, dict)]
    except (json.JSONDecodeError, AttributeError):
        pass
    return []


SERVER_DEFAULTS = {
    "business_criticality": os.environ.get("DEFAULT_BUSINESS_CRITICALITY", "High"),
    "technical_owner":      os.environ.get("DEFAULT_TECHNICAL_OWNER", "Sandeep"),
    "business_owner":       os.environ.get("DEFAULT_BUSINESS_OWNER", ""),
    "cost":                 os.environ.get("DEFAULT_COST", "High"),
    "extra_columns":        _parse_extra_columns_env(),
}


def _auth() -> dict:
    provider = session.get("provider", "bitbucket")
    auth = {
        "token":    session["password"],
        "base_url": session.get("base_url", PROVIDER_BASE_URLS.get(provider, "")),
    }
    if provider == "bitbucket":
        auth["username"] = session.get("username", "")
    return auth


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    return render_template(
        "index.html",
        defaults=SERVER_DEFAULTS,
        provider_base_urls=PROVIDER_BASE_URLS,
    )


@app.route("/workspaces", methods=["POST"])
def workspaces():
    provider = request.form.get("provider", "bitbucket").strip()
    base_url  = request.form.get("base_url", "").strip()
    username  = request.form.get("username", "").strip()
    password  = request.form.get("password", "").strip()

    if not password:
        flash("API Token is required.", "danger")
        return redirect(url_for("index"))
    if provider == "bitbucket" and not username:
        flash("Username is required for Bitbucket.", "danger")
        return redirect(url_for("index"))
    if provider == "gitea" and not base_url:
        flash("Instance URL is required for Gitea/Forgejo.", "danger")
        return redirect(url_for("index"))

    try:
        mod = get_provider(provider)
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("index"))

    # Fall back to provider's cloud default if no base_url supplied
    if not base_url:
        base_url = mod.DEFAULT_BASE_URL

    session["provider"]  = provider
    session["base_url"]  = base_url
    session["username"]  = username
    session["password"]  = password

    col_names    = request.form.getlist("extra_col_name")
    col_defaults = request.form.getlist("extra_col_default")
    session["defaults"] = {
        "business_criticality": request.form.get("business_criticality", SERVER_DEFAULTS["business_criticality"]),
        "technical_owner":      request.form.get("technical_owner",      SERVER_DEFAULTS["technical_owner"]),
        "business_owner":       request.form.get("business_owner",       SERVER_DEFAULTS["business_owner"]),
        "cost":                 request.form.get("cost",                 SERVER_DEFAULTS["cost"]),
        "extra_columns": [
            {"name": n.strip(), "default": d}
            for n, d in zip(col_names, col_defaults) if n.strip()
        ],
    }

    try:
        ws_list = mod.get_workspaces(_auth())
    except requests.HTTPError as exc:
        flash(f"Authentication failed or API error: {exc}", "danger")
        return redirect(url_for("index"))
    except requests.RequestException as exc:
        flash(f"Network error connecting to {provider}: {exc}", "danger")
        return redirect(url_for("index"))

    if not ws_list:
        flash(f"No {WORKSPACE_LABELS.get(provider, 'workspaces').lower()}s found for these credentials.", "warning")
        return redirect(url_for("index"))

    session["workspace_names"] = {ws["slug"]: ws.get("name", ws["slug"]) for ws in ws_list}
    workspace_label = WORKSPACE_LABELS.get(provider, "Workspace")
    return render_template("workspaces.html", workspaces=ws_list, workspace_label=workspace_label)


@app.route("/repos", methods=["POST"])
def repos():
    provider = session.get("provider", "bitbucket")
    selected_slugs = request.form.getlist("workspaces")
    if not selected_slugs:
        workspace_label = WORKSPACE_LABELS.get(provider, "Workspace")
        flash(f"Please select at least one {workspace_label.lower()}.", "warning")
        return redirect(url_for("index"))

    try:
        mod = get_provider(provider)
        repo_list = mod.fetch_repos_for_workspaces(selected_slugs, _auth())
    except requests.HTTPError as exc:
        flash(f"API error while fetching repositories: {exc}", "danger")
        return redirect(url_for("index"))
    except requests.RequestException as exc:
        flash(f"Network error while fetching repositories: {exc}", "danger")
        return redirect(url_for("index"))

    if not repo_list:
        workspace_label = WORKSPACE_LABELS.get(provider, "workspace")
        flash(f"No repositories found in the selected {workspace_label.lower()}(s).", "warning")
        return redirect(url_for("index"))

    for i, r in enumerate(repo_list):
        r["index"] = i

    # Build grouped tree: {workspace_slug: {project_name: {"key": str, "repos": [...]}}}
    tree = {}
    for r in repo_list:
        ws = r["workspace"]
        pname = r["project_name"]
        tree.setdefault(ws, {})
        if pname not in tree[ws]:
            tree[ws][pname] = {"key": r["project_key"], "repos": []}
        tree[ws][pname]["repos"].append(r)

    workspace_names = session.get("workspace_names", {})
    return render_template(
        "repos.html",
        tree=tree,
        workspace_names=workspace_names,
        repo_list=repo_list,
        total=len(repo_list),
    )


@app.route("/download", methods=["POST"])
def download():
    try:
        all_repos = json.loads(request.form.get("repo_data", "[]"))
    except json.JSONDecodeError:
        flash("Invalid form data.", "danger")
        return redirect(url_for("index"))

    selected_indices = set(request.form.getlist("selected"))
    selected_repos = [r for r in all_repos if str(r.get("index", -1)) in selected_indices]

    d = session.get("defaults", SERVER_DEFAULTS)

    extra_cols = d.get("extra_columns", [])
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(CSV_HEADER_FIXED + [c["name"] for c in extra_cols])
    for r in selected_repos:
        writer.writerow([
            r["clone_url"],
            r["branch"],
            "",
            r["repo_name"],
            d.get("business_criticality", ""),
            r["project_name"],
            d.get("technical_owner", ""),
            d.get("business_owner", ""),
            d.get("cost", ""),
            *[c["default"] for c in extra_cols],
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=assessment_input.csv"},
    )


# ---------------------------------------------------------------------------
# Entry point (for local dev without flask CLI)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
