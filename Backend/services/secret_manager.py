from __future__ import annotations

import os

from google.cloud import secretmanager


def get_secret(name: str, default: str = "") -> str:
    """
    Cloud-first secret accessor.
    In local/dev fallback, reads from environment variables.
    """
    value = os.getenv(name)
    if value is not None and value != "":
        return value
    project = os.getenv("GCP_PROJECT_ID")
    if project:
        try:
            client = secretmanager.SecretManagerServiceClient()
            secret_name = f"projects/{project}/secrets/{name}/versions/latest"
            response = client.access_secret_version(request={"name": secret_name})
            return response.payload.data.decode("utf-8")
        except Exception:
            pass
    return default
