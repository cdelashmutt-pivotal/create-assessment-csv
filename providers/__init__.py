"""
Provider registry for the assessment CSV generator.

Each provider module must expose:
    DEFAULT_BASE_URL: str
    get_workspaces(auth: dict) -> list[dict]
    get_repos(workspace: str, auth: dict) -> list[dict]
    fetch_repos_for_workspaces(workspace_slugs: list[str], auth: dict) -> list[dict]

The ``auth`` dict always contains ``token`` and ``base_url``.
Bitbucket additionally requires ``username``.
"""

from providers import azure_devops, bitbucket, gitea, github, gitlab

# Fixed CSV columns (provider-agnostic)
CSV_HEADER_FIXED = [
    "Repository Url",
    "Branch",
    "Subfolder",
    "App Name",
    "Business Criticality",
    "Business App",
    "Business App Technical Owner",
    "Business App Business Owner",
    "Cost",
]

_REGISTRY = {
    "bitbucket":    bitbucket,
    "github":       github,
    "gitlab":       gitlab,
    "azuredevops":  azure_devops,
    "gitea":        gitea,
}

# Human-readable labels for the "workspace" concept per provider
WORKSPACE_LABELS = {
    "bitbucket":    "Workspace",
    "github":       "Organization",
    "gitlab":       "Group",
    "azuredevops":  "Organization",
    "gitea":        "Organization",
}

# Default base URLs per provider (empty string = required, no default)
PROVIDER_BASE_URLS = {
    "bitbucket":    bitbucket.DEFAULT_BASE_URL,
    "github":       github.DEFAULT_BASE_URL,
    "gitlab":       gitlab.DEFAULT_BASE_URL,
    "azuredevops":  azure_devops.DEFAULT_BASE_URL,
    "gitea":        gitea.DEFAULT_BASE_URL,
}


def get_provider(name: str):
    """Return the provider module for the given name, or raise ValueError."""
    try:
        return _REGISTRY[name]
    except KeyError:
        raise ValueError(f"Unknown provider '{name}'. Valid options: {', '.join(_REGISTRY)}")
