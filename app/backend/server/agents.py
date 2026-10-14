"""Trigger the WAF agent Job from the Flask app and reconcile its run state.

Stdlib-only (urllib), like server.config: the Apps build proxy is flaky, so the
app must not depend on databricks-sdk. The heavy agent code runs in the Job (see
agents/), not here - the app only *triggers* it, hands it the Lakebase
coordinates to write results, and can *reconcile* a run's state against the Jobs
API if the Job dies before writing.

Each layer has its own Job, named ``waf-agent-<layer>`` by the bundle
(resources/agent_jobs.yml). The app finds it by that name through the Jobs API;
each Job grants this app's SP CAN_MANAGE_RUN, so it is visible to us. The ids
aren't injected as app resources because the Jobs run as this app's SP: the
bundle would then need the app before the Jobs and the Jobs before the app.
WAF_AGENT_JOB_ID_<LAYER> still overrides the lookup. The Job writes progress +
findings straight to Lakebase with a pure-Python driver (pg8000; see
agents/waf_agents/core/store.py) - it runs as the app SP, which owns the app
schema - so there's no app round-trip. This app just triggers the run and later
reads the results back for display.
"""

import json
import os
import urllib.parse
import urllib.request

from server.config import IS_DATABRICKS_APP, _host, _sp_oauth_token

_JOB_NAME_PREFIX = "waf-agent-"

# layer -> job id, cached per process after the first successful lookup. Misses
# aren't cached, so a Job deployed later is still picked up; a failed trigger
# evicts the entry in case the Job was recreated under a new id.
_job_ids: dict[str, str] = {}


def _lookup_job_id(layer: str) -> str | None:
    """Find the layer's Job by its exact name via the Jobs API."""
    query = urllib.parse.urlencode({"name": f"{_JOB_NAME_PREFIX}{layer}", "limit": 25})
    req = urllib.request.Request(f"{_host()}/api/2.2/jobs/list?{query}", method="GET")
    req.add_header("Authorization", f"Bearer {_sp_oauth_token()}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        jobs = json.load(resp).get("jobs", [])
    if not jobs:
        return None
    # Normally exactly one; if a stale duplicate is visible too, prefer the newest.
    return str(max(jobs, key=lambda j: j.get("created_time", 0))["job_id"])


def _job_id_for_layer(layer: str) -> str | None:
    """The deployed Job id for a layer, or None if that layer has no Job (or
    the lookup failed)."""
    override = os.environ.get(f"WAF_AGENT_JOB_ID_{layer.upper()}")
    if override:
        return override
    if layer not in _job_ids:
        try:
            job_id = _lookup_job_id(layer)
        except Exception:
            return None  # best-effort, like triggering itself
        if job_id is None:
            return None
        _job_ids[layer] = job_id
    return _job_ids[layer]


def agent_enabled(layer: str) -> bool:
    """True when the app can trigger ``layer``'s agent Job. Locally, or when the
    layer has no Job, triggering is a no-op so the app still works."""
    if not IS_DATABRICKS_APP:
        return False
    return bool(_job_id_for_layer(layer))


def trigger_agent(run_id: str, assessment_id: str, layer: str, catalogs: list[str]) -> str | None:
    """Kick off the agent Job for one assessment layer. ``run_id`` is the
    AgentRun the Job should update. Returns the Databricks job run id, or None
    if this layer has no Job configured. Never raises into the request path - a
    failed trigger must not break assessment creation."""
    if not IS_DATABRICKS_APP:
        return None
    job_id = _job_id_for_layer(layer)
    if not job_id:
        return None

    try:
        token = _sp_oauth_token()
        # The layer is baked into each Job (its wheel task), so it is not passed
        # as a run parameter - the Job you trigger determines the layer.
        params = {
            "run_id": run_id,
            "assessment_id": assessment_id,
            "catalogs": ",".join(catalogs),
            # Lakebase coordinates for the Job's direct write-back. The Job runs
            # as the app SP (owns the app schema), mints its own credential, and
            # writes agent_runs / agent_findings itself. We forward our own
            # injected connection env so the Job needn't rediscover it. Serverless
            # jobs can't take env vars, so these ride as job parameters.
            "pg_host": os.environ.get("PGHOST", ""),
            "pg_port": os.environ.get("PGPORT", "5432"),
            "pg_database": os.environ.get("PGDATABASE", "waf"),
            "pg_user": os.environ.get("PGUSER", ""),
            "pg_schema": os.environ.get("PGSCHEMA", "waf"),
            "endpoint_name": os.environ.get("ENDPOINT_NAME", ""),
        }
        payload = {"job_id": int(job_id), "job_parameters": params}
        req = urllib.request.Request(
            f"{_host()}/api/2.2/jobs/run-now",
            data=json.dumps(payload).encode(),
            method="POST",
        )
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return str(json.load(resp).get("run_id"))
    except Exception:
        # Best-effort: the caller decides how to record the failure. Forget the
        # cached id so the next trigger looks the Job up again.
        _job_ids.pop(layer, None)
        return None


def job_run_terminal_failure(job_run_id: str) -> str | None:
    """If the Databricks job run has finished *unsuccessfully*, return a short
    reason; otherwise None (still running, succeeded, or unknown).

    Used to reconcile a run stuck at 'running' because the Job crashed hard
    (e.g. OOM/SIGKILL) before it could POST a 'failed' event. Best-effort:
    any error returns None so reconciliation never breaks a read."""
    if not IS_DATABRICKS_APP:
        return None
    try:
        token = _sp_oauth_token()
        req = urllib.request.Request(
            f"{_host()}/api/2.2/jobs/runs/get?run_id={job_run_id}", method="GET"
        )
        req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=30) as resp:
            state = json.load(resp).get("state", {})
    except Exception:
        return None

    life_cycle = state.get("life_cycle_state")
    if life_cycle not in ("TERMINATED", "INTERNAL_ERROR", "SKIPPED"):
        return None  # PENDING / RUNNING / TERMINATING / BLOCKED / QUEUED
    result = state.get("result_state")
    if life_cycle == "TERMINATED" and result == "SUCCESS":
        # Job finished cleanly but we never got a 'done' POST - treat as failure
        # so the UI stops spinning rather than waiting forever.
        return "agent job finished without posting results"
    return state.get("state_message") or f"agent job {life_cycle} ({result})"
