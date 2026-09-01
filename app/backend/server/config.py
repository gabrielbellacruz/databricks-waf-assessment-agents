"""Environment detection and Lakebase credential minting.

Deliberately dependency-free (stdlib only): the Databricks Apps build fetches
wheels through a flaky internal proxy, so every avoided dependency raises the
odds the build succeeds. That rules out databricks-sdk; auth is done directly.

Two modes:
  * Inside a Databricks App - the runtime injects the app service principal's
    OAuth credentials (DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET) and host.
    We run the OAuth client-credentials flow and call the Postgres credentials
    endpoint over HTTPS.
  * Locally - we shell out to the `databricks` CLI (present on a dev machine),
    using the profile in DATABRICKS_CONFIG_PROFILE.
"""

import json
import os
import subprocess
import urllib.parse
import urllib.request

IS_DATABRICKS_APP = bool(os.environ.get("DATABRICKS_APP_NAME"))


def _host() -> str:
    host = os.environ.get("DATABRICKS_HOST", "")
    if host and not host.startswith("http"):
        host = f"https://{host}"
    return host.rstrip("/")


def _sp_oauth_token() -> str:
    """OAuth token for the app service principal via client-credentials."""
    token_url = f"{_host()}/oidc/v1/token"
    data = urllib.parse.urlencode(
        {"grant_type": "client_credentials", "scope": "all-apis"}
    ).encode()
    req = urllib.request.Request(token_url, data=data, method="POST")
    # Basic auth with client id/secret.
    import base64

    client_id = os.environ["DATABRICKS_CLIENT_ID"]
    client_secret = os.environ["DATABRICKS_CLIENT_SECRET"]
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    req.add_header("Authorization", f"Basic {basic}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)["access_token"]


def mint_database_credential(endpoint_name: str) -> str:
    """Mint a short-lived Lakebase OAuth token for the given endpoint path."""
    if IS_DATABRICKS_APP:
        token = _sp_oauth_token()
        url = f"{_host()}/api/2.0/postgres/credentials"
        body = json.dumps({"endpoint": endpoint_name}).encode()
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)["token"]

    # Local: use the CLI (avoids bundling the SDK just for dev).
    profile = os.environ.get("DATABRICKS_CONFIG_PROFILE", "DEFAULT")
    out = subprocess.run(
        [
            "databricks", "postgres", "generate-database-credential",
            endpoint_name, "-p", profile, "-o", "json",
        ],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)["token"]
