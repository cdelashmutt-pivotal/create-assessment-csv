# Repository Assessment CSV Generator

Generates a CSV file in the format expected by the Tanzu assessment import template, populated with repositories from Bitbucket Cloud.

Two modes are available:

- **CLI script** — run locally, outputs a file
- **Web UI** — a Flask wizard you can run locally or deploy to any Cloud Foundry-compatible platform

---

## Prerequisites

- Python 3.12+
- A Bitbucket Cloud account with access to the workspaces you want to export

### Bitbucket API Token

The tool authenticates with a Bitbucket API Token scoped to the minimum required permissions.

1. Click your **profile picture** in Bitbucket → **Security**
2. Under "API tokens", select **Create API Token with Scopes**
3. Choose the **BitBucket** app and enable these scopes:
   - `read:account`
   - `read:workspace:bitbucket`
   - `read:project:bitbucket`
   - `read:repository:bitbucket`
4. Copy the generated token — you will not be able to view it again

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

```bash
python generate_assessment_csv.py
```

You will be prompted for your Bitbucket username and API token. The token is entered silently (no echo).

```
Bitbucket API Token required.
  Profile picture → Security → Create API Token with Scopes (BitBucket app)
  Scopes: read:account, read:workspace:bitbucket, read:project:bitbucket, read:repository:bitbucket

Bitbucket username: jdoe
API Token:
Processing 3 workspace(s): my-workspace, another-workspace, shared-workspace

Done. Wrote 142 row(s) to assessment_input.csv
```

The output file `assessment_input.csv` is written to the current directory.

### Configuration

Open `generate_assessment_csv.py` and edit the values in the configuration block near the top of the file:

| Variable | Default | Description |
|---|---|---|
| `WORKSPACES` | `[]` | List of workspace slugs to export. Leave empty to auto-discover all workspaces the user belongs to. |
| `DEFAULT_BUSINESS_CRITICALITY` | `High` | Applied to every row |
| `DEFAULT_TECHNICAL_OWNER` | `Sandeep` | Applied to every row |
| `DEFAULT_BUSINESS_OWNER` | _(empty)_ | Applied to every row |
| `DEFAULT_COST` | `High` | Applied to every row |
| `DEFAULT_PROGRAM` | _(empty)_ | Applied to every row |
| `DEFAULT_INVESTMENT_STATUS` | _(empty)_ | Applied to every row |
| `OUTPUT_FILE` | `assessment_input.csv` | Output file path |

---

## Web UI — Local

```bash
pip install -r requirements.txt
flask run
```

Then open [http://localhost:5000](http://localhost:5000).

The wizard walks through four steps: connect, select workspaces, review repositories, and download the CSV.

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
| Business App | Bitbucket project name |
| Business App Technical Owner | Configured default |
| Business App Business Owner | Configured default |
| Cost | Configured default |
| Program | Configured default |
| Investment Status | Configured default |
