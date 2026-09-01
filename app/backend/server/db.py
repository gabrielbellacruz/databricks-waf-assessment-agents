"""Lakebase (Postgres) access via Flask-SQLAlchemy.

Lakebase auth is a short-lived OAuth token, not a static password: the token
expires after ~1 hour and must be minted fresh. So instead of baking a password
into the SQLAlchemy URL, we leave the password out of the URL and inject a freshly
minted token on every physical connection via the `do_connect` event. That keeps
tokens from going stale no matter how long the pool lives.

`pool_recycle` (2700s / 45 min) discards connections before the 1-hour token
expiry so a long-idle connection is never used with a dead token.

Environment (injected by the Databricks App runtime when a database resource is
attached, except ENDPOINT_NAME which we set in app.yaml):
  PGHOST, PGUSER, PGPORT, PGDATABASE  - connection coordinates
  ENDPOINT_NAME                        - Lakebase endpoint path for credential minting
Locally these come from the shell / .env (see server.config for the CLI fallback).
"""

import os

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event

from server.config import mint_database_credential

db = SQLAlchemy()


def app_schema() -> str:
    """Schema the app owns and puts all its objects in.

    A Databricks App connects as its own service principal, which has
    CAN_CONNECT_AND_CREATE but does not own the pre-existing `public` schema
    (owned by the database owner). Writing into `public` fails with
    "permission denied for schema public". Instead the SP creates and owns this
    dedicated schema (see migrations/env.py) and every connection is pinned to
    it via search_path.
    """
    return os.environ.get("PGSCHEMA", "waf")


def database_url() -> str:
    """Build the SQLAlchemy URL without a password.

    The password (a fresh OAuth token) is injected per-connection by the
    `do_connect` listener registered in `register_token_injection`.
    """
    host = os.environ["PGHOST"]
    port = os.environ.get("PGPORT", "5432")
    database = os.environ.get("PGDATABASE", "waf")
    user = os.environ["PGUSER"]
    return f"postgresql+psycopg2://{user}@{host}:{port}/{database}"


def register_token_injection(app) -> None:
    """Inject a fresh Lakebase OAuth token as the password on every connect.

    Must be called inside an app context so `db.engine` is resolvable. Also
    forces sslmode=require, which Lakebase mandates.
    """
    with app.app_context():
        engine = db.engine

    @event.listens_for(engine, "do_connect")
    def _provide_token(dialect, conn_rec, cargs, cparams):  # noqa: ANN001
        cparams["password"] = mint_database_credential(os.environ["ENDPOINT_NAME"])
        cparams.setdefault("sslmode", os.environ.get("PGSSLMODE", "require"))
        # Pin every session to the app-owned schema so unqualified table names
        # (and Alembic's version table) resolve there, never `public`.
        cparams["options"] = f"-c search_path={app_schema()}"
