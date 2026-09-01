"""Job entrypoint.

Invoked by the DAB serverless Job (and runnable locally for validation):

    waf-agent --run-id <run> --assessment-id <id> --layer ingestion \
        --warehouse-id <wh> [--catalogs main,prod] \
        [--pg-host <h> --pg-database <db> --pg-user <u> --endpoint-name <ep>]

Builds the execution context, runs the layer agent's LangGraph workflow, and -
when Lakebase coordinates are present - writes progress and findings + run
status straight to Lakebase (pure-Python pg8000; see core/store.py). Without DB
coordinates it prints findings as JSON, which is how we validate a check against
a real workspace before any plumbing exists.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from waf_agents.core.clients import (
    AgentContext,
    DatabricksArtifactClient,
    DatabricksSqlClient,
    ServingEndpointLlm,
)
from waf_agents.core.factory import create_agent
from waf_agents.core.store import DbConfig, ResultsStore


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="waf-agent")
    p.add_argument("--run-id", default=os.environ.get("WAF_RUN_ID", ""))
    p.add_argument("--assessment-id", required=True)
    p.add_argument("--layer", required=True)
    p.add_argument("--warehouse-id", default=os.environ.get("WAF_WAREHOUSE_ID", ""))
    p.add_argument("--catalogs", default="", help="comma-separated; empty = all visible")
    p.add_argument("--profile", default=os.environ.get("DATABRICKS_CONFIG_PROFILE"))
    # Serving endpoint for LLM-judged checks. Empty disables the LLM (those
    # checks then return 'unassessed'). The app forwards the bundle's model var.
    p.add_argument(
        "--model",
        default=os.environ.get("WAF_ASSESSMENT_MODEL", "databricks-claude-opus-4-8"),
    )
    # Lakebase coordinates for the direct write-back. Serverless jobs can't set
    # env vars, so the app forwards these as job parameters at run-now time (it
    # knows them from its own injected env). Empty => local dry-run (print).
    p.add_argument("--pg-host", default=os.environ.get("PGHOST", ""))
    p.add_argument("--pg-port", default=os.environ.get("PGPORT", "5432"))
    p.add_argument("--pg-database", default=os.environ.get("PGDATABASE", "waf"))
    p.add_argument("--pg-user", default=os.environ.get("PGUSER", ""))
    p.add_argument("--pg-schema", default=os.environ.get("PGSCHEMA", "waf"))
    p.add_argument("--endpoint-name", default=os.environ.get("ENDPOINT_NAME", ""))
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    catalogs = [c.strip() for c in args.catalogs.split(",") if c.strip()]

    ctx = AgentContext(
        assessment_id=args.assessment_id,
        layer=args.layer,
        sql=DatabricksSqlClient(warehouse_id=args.warehouse_id, profile=args.profile),
        catalogs=catalogs,
        artifacts=DatabricksArtifactClient(profile=args.profile),
        llm=ServingEndpointLlm(args.model, profile=args.profile) if args.model else None,
    )
    agent = create_agent(args.layer)
    cfg = DbConfig(
        host=args.pg_host,
        port=int(args.pg_port or 5432),
        database=args.pg_database,
        user=args.pg_user,
        schema=args.pg_schema,
        endpoint_name=args.endpoint_name,
    )
    store = ResultsStore(cfg, args.run_id, args.assessment_id, args.layer)

    # Local/validation dry-run: no DB coordinates and no run id -> just print.
    if not (store.available and args.run_id):
        print(json.dumps([f.to_dict() for f in agent.run(ctx)], indent=2))
        return 0

    run_id = args.run_id
    print(f"[waf-agent] run_id={run_id} layer={args.layer} - writing to Lakebase", flush=True)
    try:
        first = {"seen": False}

        def on_progress(done: int, total: int) -> None:
            if not first["seen"]:
                store.mark_running(total)
                first["seen"] = True
                print(f"[waf-agent] running: {total} questions", flush=True)
            store.update_progress(done)

        findings = agent.run(ctx, progress=on_progress)
        print(f"[waf-agent] computed {len(findings)} findings; writing", flush=True)
        store.write_done(findings)
        print("[waf-agent] done", flush=True)
        return 0
    except Exception as exc:  # record failure so the UI stops showing "running"
        print(f"[waf-agent] FAILED: {exc}", flush=True)
        try:
            store.mark_failed(str(exc))
        except Exception as mark_exc:
            print(f"[waf-agent] could not record failure: {mark_exc}", flush=True)
        raise
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
