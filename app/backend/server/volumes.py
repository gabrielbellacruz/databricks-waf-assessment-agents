"""Store uploaded architecture documents in a UC Volume.

The bytes go to a UC Volume (declared in the bundle, granted to the app SP);
Lakebase keeps only metadata + extracted text (see server/models.py). The agent
Jobs read the same Volume back via the SDK (agents/waf_agents/core/context.py).

Dual-mode, mirroring server.config (stdlib only - no databricks-sdk, for the
flaky Apps build proxy):
  * Inside a Databricks App - PUT/GET/DELETE via the Files API over HTTPS with
    the app service principal's OAuth token.
  * Locally - shell out to the `databricks` CLI, which handles host + auth from
    the active profile.

The Volume location comes from three env vars (set in app.yaml, matching the
bundle's docs_catalog / docs_schema / docs_volume). When they are unset,
``documents_enabled`` is False and the routes report the feature as unavailable
(like the agents do locally without a Job).
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request

from server.config import IS_DATABRICKS_APP, _host, _sp_oauth_token


def volume_root() -> str | None:
    """The ``/Volumes/<catalog>/<schema>/<volume>`` root, or None if unconfigured."""
    catalog = os.environ.get("DOCS_CATALOG")
    schema = os.environ.get("DOCS_SCHEMA")
    volume = os.environ.get("DOCS_VOLUME")
    if not (catalog and schema and volume):
        return None
    return f"/Volumes/{catalog}/{schema}/{volume}"


def documents_enabled() -> bool:
    """True when uploads can be stored: the Volume is configured and we have a
    way to reach it (an App SP token, or a CLI profile locally)."""
    if volume_root() is None:
        return False
    if IS_DATABRICKS_APP:
        return True
    return bool(os.environ.get("DATABRICKS_CONFIG_PROFILE"))


def document_path(assessment_id: str, doc_id: str, ext: str) -> str:
    """Absolute Volume path for one document. ``assessment_id``/``doc_id`` are
    slug-safe (``assessment-<hex>`` / ``doc-<hex>``) so the path needs no
    escaping; ``ext`` includes the leading dot (or is empty)."""
    root = volume_root()
    if root is None:
        raise RuntimeError("document storage is not configured")
    return f"{root}/assessments/{assessment_id}/{doc_id}{ext}"


# -- Files API (in-app) --------------------------------------------------

def _files_url(path: str) -> str:
    quoted = urllib.parse.quote(path, safe="/")
    return f"{_host()}/api/2.0/fs/files{quoted}"


def _api_upload(path: str, data: bytes) -> None:
    req = urllib.request.Request(
        f"{_files_url(path)}?overwrite=true", data=data, method="PUT"
    )
    req.add_header("Authorization", f"Bearer {_sp_oauth_token()}")
    req.add_header("Content-Type", "application/octet-stream")
    try:
        with urllib.request.urlopen(req, timeout=60):
            return
    except urllib.error.HTTPError as exc:
        # Surface the Databricks error (status + body) so callers can log the real
        # cause - e.g. PERMISSION_DENIED (SP lacks USE CATALOG / WRITE VOLUME) or
        # RESOURCE_DOES_NOT_EXIST (Volume path wrong) - instead of a blank 502.
        body = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"Files API PUT {path} failed ({exc.code}): {body}") from exc


def _api_download(path: str) -> bytes:
    req = urllib.request.Request(_files_url(path), method="GET")
    req.add_header("Authorization", f"Bearer {_sp_oauth_token()}")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def _api_delete(path: str) -> None:
    req = urllib.request.Request(_files_url(path), method="DELETE")
    req.add_header("Authorization", f"Bearer {_sp_oauth_token()}")
    with urllib.request.urlopen(req, timeout=30):
        return


# -- CLI (local dev) -----------------------------------------------------

def _cli_base() -> list[str]:
    profile = os.environ.get("DATABRICKS_CONFIG_PROFILE", "DEFAULT")
    return ["databricks", "fs", "--profile", profile]


def _cli_upload(path: str, data: bytes) -> None:
    with tempfile.NamedTemporaryFile() as tmp:
        tmp.write(data)
        tmp.flush()
        result = subprocess.run(
            [*_cli_base(), "cp", tmp.name, f"dbfs:{path}", "--overwrite"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"databricks fs cp to {path} failed: {result.stderr.strip()[:500]}"
            )


def _cli_download(path: str) -> bytes:
    with tempfile.NamedTemporaryFile() as tmp:
        subprocess.run(
            [*_cli_base(), "cp", f"dbfs:{path}", tmp.name, "--overwrite"],
            capture_output=True, text=True, check=True,
        )
        with open(tmp.name, "rb") as f:
            return f.read()


def _cli_delete(path: str) -> None:
    subprocess.run(
        [*_cli_base(), "rm", f"dbfs:{path}"],
        capture_output=True, text=True, check=True,
    )


# -- public API ----------------------------------------------------------

def upload(path: str, data: bytes) -> None:
    (_api_upload if IS_DATABRICKS_APP else _cli_upload)(path, data)


def download(path: str) -> bytes:
    return (_api_download if IS_DATABRICKS_APP else _cli_download)(path)


def delete(path: str) -> None:
    # Best-effort: a missing object shouldn't block deleting the metadata row.
    try:
        (_api_delete if IS_DATABRICKS_APP else _cli_delete)(path)
    except Exception:
        pass
