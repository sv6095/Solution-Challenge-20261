from __future__ import annotations

import os


def get_secret(name: str, default: str = "") -> str:
    """
    Cloud-first secret accessor.

    Priority:
      1. Environment variable (always checked first — works in dev with no GCP).
      2. GCP Secret Manager (only attempted when GCP_PROJECT_ID is set and
         google-cloud-secret-manager is installed).
      3. Returns `default`.
    """
    value = os.getenv(name)
    if value is not None and value != "":
        return value

    project = (os.getenv("GCP_PROJECT_ID") or "").strip()
    if project:
        try:
            from google.cloud import secretmanager  # type: ignore[import]
            client = secretmanager.SecretManagerServiceClient()
            secret_name = f"projects/{project}/secrets/{name}/versions/latest"
            response = client.access_secret_version(request={"name": secret_name})
            return response.payload.data.decode("utf-8")
        except Exception:
            pass

    return default
