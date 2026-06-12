# Repository Assessment CSV Generator

Generates a CSV file in the format expected by the Tanzu assessment import template, populated with repositories from your Git provider.

**Supported providers:** Bitbucket Cloud, GitHub, GitLab, Azure DevOps, Gitea / Forgejo.
Self-hosted / on-premises instances are supported for all providers via a configurable base URL.

Two modes are available:

- **CLI script** — run locally, outputs a file
- **Web UI** — a Flask wizard you can run locally or deploy to any Cloud Foundry-compatible platform

---

## Prerequisites

- Python 3.12+
- An account on your chosen Git provider with read access to the repositories you want to export

### API Tokens

Each provider uses a Personal Access Token (or API Token) for authentication.
Only the minimum read scopes are required.

#### Bitbucket Cloud

1. Click your **profile picture** → **Security**
2. Under "API tokens", select **Create API Token with Scopes**
3. Choose the **BitBucket** app and enable these scopes:
   - `read:account`
   - `read:workspace:bitbucket`
   - `read:project:bitbucket`
   - `read:repository:bitbucket`
4. Copy the generated token — you will not be able to view it again

#### GitHub / GitHub Enterprise Server

1. Go to **Settings → Developer settings → Personal access tokens**
2. Create a token with scopes: `repo` (or `read:org` + `read:user` for org repos only)

#### GitLab / GitLab self-managed

1. Go to **User Settings → Access Tokens**
2. Create a token with scope: `read_api`

#### Azure DevOps Services / Azure DevOps Server

1. Go to **User settings → Personal access tokens** in Azure DevOps
2. Create a token with scopes: **Code (Read)**, **Project and Team (Read)**

#### Gitea / Forgejo

1. Go to **Settings → Applications → Manage Access Tokens**
2. Create a token with scopes: `read:organization`, `read:repository`, `read:user`

---

## CLI Usage

### Install dependencies

```bash
pip install -r requirements.txt
```

Or using the vendored wheels (no internet required):

```bash
pip install --no-index --find-links vendor -r requirements.txt
```

### Run

The script prompts interactively for credentials. The default provider is Bitbucket.

```bash
python generate_assessment_csv.py
```

Use `--provider` to target a different provider:

```bash
# GitHub
python generate_assessment_csv.py --provider github --token <PAT>

# GitLab
python generate_assessment_csv.py --provider gitlab --token <PAT>

# Azure DevOps
python generate_assessment_csv.py --provider azuredevops --token <PAT>

# Gitea / Forgejo (instance URL required)
python generate_assessment_csv.py --provider gitea --base-url https://gitea.example.com --token <tok>

# Self-hosted GitLab
python generate_assessment_csv.py --provider gitlab --base-url https://gitlab.example.com --token <PAT>

# Specific orgs / workspaces only
python generate_assessment_csv.py --provider github --token <PAT> --workspaces my-org,another-org
```

All flags:

| Flag | Description |
|---|---|
| `--provider` | `bitbucket` (default), `github`, `gitlab`, `azuredevops`, `gitea` |
| `--base-url` | Self-hosted or enterprise instance URL (e.g. `https://github.example.com`). Omit for public cloud providers. Required for Gitea/Forgejo. |
| `--token` | API / Personal Access Token (prompted interactively if omitted) |
| `--username` | Username — Bitbucket only (prompted interactively if omitted) |
| `--workspaces` | Comma-separated workspace / org / group slugs to export (auto-discovers all if omitted) |
| `--output` | Output CSV file path (default: `assessment_input.csv`) |

The output file is written to the current directory (or the path given by `--output`).

### Configuration

Open `generate_assessment_csv.py` and edit the values in the configuration block near the top of the file to set persistent defaults without using flags:

| Variable | Default | Description |
|---|---|---|
| `WORKSPACES` | `[]` | List of workspace / org / group slugs to export. Leave empty to auto-discover all. |
| `DEFAULT_BUSINESS_CRITICALITY` | `High` | Applied to every row |
| `DEFAULT_TECHNICAL_OWNER` | `Sandeep` | Applied to every row |
| `DEFAULT_BUSINESS_OWNER` | _(empty)_ | Applied to every row |
| `DEFAULT_COST` | `High` | Applied to every row |
| `EXTRA_COLUMNS` | `[]` | Additional columns appended after "Cost". Each entry is `{"name": "Column Name", "default": "value"}`. |
| `OUTPUT_FILE` | `assessment_input.csv` | Output file path |

---

## Web UI — Local

```bash
pip install -r requirements.txt
flask run
```

Then open [http://localhost:5000](http://localhost:5000).

The wizard walks through three steps:

1. **Connect** — select your Git provider, enter the API base URL (pre-filled with the cloud default; edit for self-hosted instances), and provide your credentials
2. **Select workspaces / organizations / groups** — the tool discovers and lists what the token has access to; tick the ones to scan
3. **Review repositories & download** — toggle individual repos on or off, then download the CSV

The credential form adapts to the selected provider: the username field only appears for Bitbucket, labels and help text update to match each provider's terminology, and the base URL field is pre-filled with the cloud default so you only need to change it for self-hosted instances.

---

## Web UI — Cloud Foundry Deployment

The app includes a `manifest.yml` and is ready to push to any Cloud Foundry-compatible platform, including:

- **Tanzu Hub**
- **Tanzu Evaluation Appliances**
- **Tanzu Platform Elastic Runtime**
- **Open source Cloud Foundry**

### Push

```bash
cf login -a <API_ENDPOINT>
cf target -o <ORG> -s <SPACE>
cf push
```

The `manifest.yml` configures the app name (`repo-assessment-csv`), memory (256 MB), and the Gunicorn startup command. The Python buildpack is used automatically.

### Tanzu Hub / Tanzu Evaluation Appliance / Tanzu Platform Elastic Runtime

Log in with the API endpoint provided for your environment:

```bash
cf login -a https://api.<your-system-domain>
cf target -o <ORG> -s <SPACE>
cf push
```

### Environment variables

CSV default values can be overridden at deploy time without touching the code:

```bash
cf set-env repo-assessment-csv DEFAULT_TECHNICAL_OWNER "Jane Smith"
cf set-env repo-assessment-csv DEFAULT_BUSINESS_CRITICALITY "Medium"
cf restage repo-assessment-csv
```

If you scale beyond one instance, set a fixed `SECRET_KEY` so user sessions remain valid across instances:

```bash
cf set-env repo-assessment-csv SECRET_KEY $(python -c "import secrets; print(secrets.token_hex(32))")
cf restage repo-assessment-csv
```

### Vendored dependencies

The `vendor/` directory contains pre-downloaded wheels for all major platforms, so no internet access to PyPI is required at deploy or install time. The Python buildpack picks them up automatically.

| Package | Platforms included |
|---|---|
| `markupsafe` | Linux x86_64, Linux arm64, macOS (universal2), Windows x64 |
| `charset_normalizer` | Linux x86_64, Linux arm64, macOS (universal2), Windows x64, pure-Python fallback |
| All others | Pure Python (`py3-none-any`) — works everywhere |

> **Note:** `MarkupSafe` on macOS ships as version 2.1.5 (the latest available macOS binary). Linux and Windows use 3.0.3. Both are fully compatible with the Flask/Jinja2 versions in use.

To refresh the vendor directory after updating `requirements.txt`:

```bash
# Pure-Python and Linux x86_64 wheels (covers CF/Tanzu deployments)
pip download -r requirements.txt -d vendor

# Add wheels for the remaining platforms
pip download --only-binary=:all: --python-version 3.12 --abi cp312 --platform manylinux2014_aarch64  -d vendor markupsafe charset_normalizer
pip download --only-binary=:all: --python-version 3.12 --abi cp312 --platform macosx_10_9_universal2 -d vendor markupsafe charset_normalizer
pip download --only-binary=:all: --python-version 3.12 --abi cp312 --platform win_amd64             -d vendor markupsafe charset_normalizer
```

---

## CSV Format

The output CSV contains one row per repository with the following columns:

| Column | Source |
|---|---|
| Repository Url | HTTPS clone URL |
| Branch | Default branch |
| Subfolder | _(empty — fill in manually if needed)_ |
| App Name | Repository name |
| Business Criticality | Configured default |
| Business App | Project / group / org name (see below) |
| Business App Technical Owner | Configured default |
| Business App Business Owner | Configured default |
| Cost | Configured default |
| _(custom columns)_ | Configured defaults — any columns added via `EXTRA_COLUMNS` or the web UI |

#### Business App — per-provider mapping

| Provider | Business App source |
|---|---|
| Bitbucket | Bitbucket Project name |
| GitHub | Organization name (repos are flat within an org) |
| GitLab | Immediate namespace (group or subgroup) name |
| Azure DevOps | Azure DevOps Project name |
| Gitea / Forgejo | Organization name (repos are flat within an org) |
