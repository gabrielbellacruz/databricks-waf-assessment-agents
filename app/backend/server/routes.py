"""HTTP routes: assessment CRUD under /api + the static PWA everywhere else.

JSON is camelCase to match the frontend `Assessment` type. The compiled React
PWA is served from `static/`, with an index.html fallback so client-side routes
survive a refresh or a deep link.
"""

import mimetypes
import os
import re
import threading
import time
from datetime import datetime, timezone

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    jsonify,
    request,
    send_from_directory,
)

from server import extract, volumes
from server.agents import agent_enabled, job_run_terminal_failure, trigger_agent
from server.backlog import backlog_enabled, generate_backlog
from server.db import db
from server.models import (
    AgentFinding,
    AgentRun,
    ArchitectureDocument,
    Assessment,
    BacklogRun,
)

# Layers that have an agent available to run.
_AGENT_LAYERS = {
    "ingestion",
    "storage",
    "processing",
    "orchestration",
    "analytics",
    "ai",
    "ml",
}

# Correct MIME types for PWA registration (service worker, manifest, svg).
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("image/svg+xml", ".svg")

_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")  # guard path-derived assessment ids

api = Blueprint("api", __name__, url_prefix="/api")
site = Blueprint("site", __name__)


def _valid_id(assessment_id: str) -> str:
    if not _ID_RE.match(assessment_id):
        abort(400, description="Invalid id")
    return assessment_id


def _start_agent_run(assessment_id: str, layer: str, catalogs: list[str]) -> AgentRun | None:
    """Start (or reuse) an agent run for one assessment layer.

    Single-flight: if a run for this (assessment, layer) is already queued or
    running, return it rather than starting a second. Returns None when the
    agent can't be triggered (e.g. local dev without a Job), so callers treat
    "no run" gracefully. Never raises - triggering is best-effort.
    """
    if layer not in _AGENT_LAYERS or not agent_enabled(layer):
        return None

    existing = db.session.execute(
        db.select(AgentRun)
        .where(
            AgentRun.assessment_id == assessment_id,
            AgentRun.layer == layer,
            AgentRun.status.in_(("queued", "running")),
        )
        .order_by(AgentRun.started_at.desc())
    ).scalar()
    if existing is not None:
        return existing

    run = AgentRun(assessment_id=assessment_id, layer=layer, status="queued")
    db.session.add(run)
    db.session.flush()  # assign run_id before we hand it to the Job

    run.job_run_id = trigger_agent(run.run_id, assessment_id, layer, catalogs)
    db.session.commit()
    return run


def _start_agents_for_assessment(assessment: Assessment) -> list[str]:
    """Kick off agents for every in-scope layer that has one, returning the layers
    for which a run was started (or reused). The frontend stores categories as
    display names ("Ingestion"); the agent layer / category id is the lowercase
    form ("ingestion"), which is also how findings are keyed and fetched. Normalize
    before matching. Best-effort: a trigger failure never fails the caller."""
    started: list[str] = []
    for category in assessment.categories or []:
        layer = category.lower()
        if layer in _AGENT_LAYERS and _start_agent_run(
            assessment.id, layer, catalogs=[]
        ) is not None:
            started.append(layer)
    return started


# Rate-limit Jobs-API reconciliation so the frontend's fast polling doesn't hit
# the API every few seconds. run_id -> monotonic timestamp of last check.
_RECONCILE_MIN_INTERVAL_S = 10.0
_last_reconcile: dict[str, float] = {}


def _reconcile_run(run: AgentRun) -> None:
    """If an active run's Job has died without posting a terminal event, mark it
    failed so the UI stops spinning. No-op unless the run is queued/running with
    a known job run id, and throttled to one Jobs-API call per run per interval."""
    if run.status not in ("queued", "running") or not run.job_run_id:
        return
    now = time.monotonic()
    if now - _last_reconcile.get(run.run_id, 0.0) < _RECONCILE_MIN_INTERVAL_S:
        return
    _last_reconcile[run.run_id] = now

    reason = job_run_terminal_failure(run.job_run_id)
    if reason:
        run.status = "failed"
        run.error = reason[:2000]
        run.finished_at = db.func.now()
        db.session.commit()


# -- API -----------------------------------------------------------------

@api.get("/assessments")
def list_assessments():
    rows = (
        db.session.execute(
            db.select(Assessment).order_by(Assessment.updated_at.desc())
        )
        .scalars()
        .all()
    )
    return jsonify([a.to_dict() for a in rows])


@api.post("/assessments")
def create_assessment():
    body = request.get_json(silent=True) or {}
    assessment = Assessment(
        name=body.get("name", ""),
        description=body.get("description", ""),
        categories=body.get("categories", []),
        cloud_provider=body.get("cloudProvider"),
        imported_at=body.get("importedAt"),
        answers=body.get("answers", {}),
        notes=body.get("notes", {}),
    )
    db.session.add(assessment)
    db.session.commit()

    # Kick off the layer agents unless the caller defers it. The create-with-docs
    # flow passes runAgents=false so the user can attach architecture documents
    # first, then triggers them via POST .../agents/run so the first run sees the
    # docs. Other callers (import) keep the default and run agents immediately.
    if body.get("runAgents", True):
        _start_agents_for_assessment(assessment)

    return jsonify(assessment.to_dict()), 201


@api.put("/assessments/<assessment_id>")
def update_assessment(assessment_id: str):
    assessment = db.session.get(Assessment, _valid_id(assessment_id))
    if assessment is None:
        abort(404, description="Assessment not found")
    body = request.get_json(silent=True) or {}
    assessment.name = body.get("name", "")
    assessment.description = body.get("description", "")
    assessment.categories = body.get("categories", [])
    assessment.cloud_provider = body.get("cloudProvider")
    db.session.commit()
    return jsonify(assessment.to_dict())


@api.delete("/assessments/<assessment_id>")
def delete_assessment(assessment_id: str):
    assessment = db.session.get(Assessment, _valid_id(assessment_id))
    if assessment is not None:
        db.session.delete(assessment)
        db.session.commit()
    return "", 204


@api.put("/assessments/<assessment_id>/answers")
def set_status(assessment_id: str):
    # Read-modify-write under a row lock: the answers tree is sparse, so mutate
    # in Python rather than with jsonb_set (which can't create intermediate keys).
    body = request.get_json(silent=True) or {}
    assessment = db.session.execute(
        db.select(Assessment)
        .where(Assessment.id == _valid_id(assessment_id))
        .with_for_update()
    ).scalar_one_or_none()
    if assessment is None:
        abort(404, description="Assessment not found")

    # Copy-then-reassign so SQLAlchemy sees the JSONB column as dirty (it does not
    # track in-place mutation of a plain dict).
    answers = dict(assessment.answers or {})
    category = dict(answers.get(body["categoryId"], {}))
    pillar = dict(category.get(body["pillarId"], {}))
    pillar[body["questionId"]] = body["status"]
    category[body["pillarId"]] = pillar
    answers[body["categoryId"]] = category
    assessment.answers = answers

    db.session.commit()
    return jsonify(assessment.to_dict())


@api.put("/assessments/<assessment_id>/notes")
def set_note(assessment_id: str):
    # Same read-modify-write under a row lock as set_status: the notes tree is
    # sparse, so mutate in Python. An empty note prunes the entry so the tree
    # stays clean (and empty branches collapse away).
    body = request.get_json(silent=True) or {}
    assessment = db.session.execute(
        db.select(Assessment)
        .where(Assessment.id == _valid_id(assessment_id))
        .with_for_update()
    ).scalar_one_or_none()
    if assessment is None:
        abort(404, description="Assessment not found")

    category_id = body["categoryId"]
    pillar_id = body["pillarId"]
    question_id = body["questionId"]
    note = body.get("note", "")

    # Copy-then-reassign so SQLAlchemy sees the JSONB column as dirty.
    notes = dict(assessment.notes or {})
    category = dict(notes.get(category_id, {}))
    pillar = dict(category.get(pillar_id, {}))

    if isinstance(note, str) and note.strip():
        pillar[question_id] = note
    else:
        pillar.pop(question_id, None)

    # Collapse empty branches so the tree mirrors the sparse frontend shape.
    if pillar:
        category[pillar_id] = pillar
    else:
        category.pop(pillar_id, None)
    if category:
        notes[category_id] = category
    else:
        notes.pop(category_id, None)
    assessment.notes = notes

    db.session.commit()
    return jsonify(assessment.to_dict())


# -- agents --------------------------------------------------------------

@api.post("/assessments/<assessment_id>/agents/run")
def run_agents(assessment_id: str):
    """Trigger (or reuse) agents for every in-scope layer at once. The create
    flow calls this after the user has optionally attached architecture documents,
    so the first run sees them. Best-effort, mirroring assessment creation."""
    assessment = db.session.get(Assessment, _valid_id(assessment_id))
    if assessment is None:
        abort(404, description="Assessment not found")
    started = _start_agents_for_assessment(assessment)
    return jsonify({"started": started}), 202


@api.post("/assessments/<assessment_id>/agents/<layer>/run")
def run_agent(assessment_id: str, layer: str):
    """Trigger (or reuse) an agent run for a layer. Refresh uses this too."""
    assessment = db.session.get(Assessment, _valid_id(assessment_id))
    if assessment is None:
        abort(404, description="Assessment not found")
    if layer not in _AGENT_LAYERS:
        abort(404, description="No agent for this layer")

    run = _start_agent_run(assessment_id, layer, catalogs=[])
    if run is None:
        # Agent not available in this environment (e.g. local dev).
        return jsonify({"enabled": False}), 202
    return jsonify(run.to_dict()), 202


@api.get("/assessments/<assessment_id>/agents/<layer>/run")
def get_agent_run(assessment_id: str, layer: str):
    """Latest run for a layer, for the frontend to poll. 204 when none exists."""
    run = db.session.execute(
        db.select(AgentRun)
        .where(AgentRun.assessment_id == _valid_id(assessment_id), AgentRun.layer == layer)
        .order_by(AgentRun.started_at.desc())
    ).scalar()
    if run is None:
        return "", 204
    _reconcile_run(run)
    return jsonify(run.to_dict())


@api.get("/assessments/<assessment_id>/agents/<layer>/findings")
def get_agent_findings(assessment_id: str, layer: str):
    """Findings from the latest run for a layer, keyed by question id."""
    run = db.session.execute(
        db.select(AgentRun)
        .where(AgentRun.assessment_id == _valid_id(assessment_id), AgentRun.layer == layer)
        .order_by(AgentRun.started_at.desc())
    ).scalar()
    if run is None:
        return jsonify({"run": None, "findings": {}})
    _reconcile_run(run)

    rows = (
        db.session.execute(
            db.select(AgentFinding).where(AgentFinding.run_id == run.run_id)
        )
        .scalars()
        .all()
    )
    return jsonify(
        {
            "run": run.to_dict(),
            "findings": {f.question_id: f.to_dict() for f in rows},
        }
    )


# -- backlog agent -------------------------------------------------------

# A backlog run has no Databricks Job to poll, so a stuck run is reconciled by
# elapsed wall-clock time instead (worker died mid-run, redeploy, etc.). Kept
# safely above the model call's own timeout (~300s in server/backlog.py) so a
# slow-but-live run resolves itself before this would prematurely fail it.
_BACKLOG_STALE_SECONDS = 420.0


def _latest_backlog_run(assessment_id: str) -> BacklogRun | None:
    return db.session.execute(
        db.select(BacklogRun)
        .where(BacklogRun.assessment_id == assessment_id)
        .order_by(BacklogRun.started_at.desc())
    ).scalar()


@api.post("/assessments/<assessment_id>/backlog/run")
def run_backlog(assessment_id: str):
    """Generate (or reuse an in-flight) implementation backlog for an assessment.

    The request body carries the assembled results context the frontend already
    has; the app enriches it with agent findings and prompts the model in a
    background thread."""
    assessment = db.session.get(Assessment, _valid_id(assessment_id))
    if assessment is None:
        abort(404, description="Assessment not found")
    if not backlog_enabled():
        # Needs the app SP token to call the model; no-op locally, like the agents.
        return jsonify({"enabled": False}), 202

    # Single-flight: reuse a run that is still queued or running.
    existing = db.session.execute(
        db.select(BacklogRun)
        .where(
            BacklogRun.assessment_id == assessment_id,
            BacklogRun.status.in_(("queued", "running")),
        )
        .order_by(BacklogRun.started_at.desc())
    ).scalar()
    if existing is not None:
        return jsonify(existing.to_dict()), 202

    context = request.get_json(silent=True) or {}
    run = BacklogRun(assessment_id=assessment_id, status="queued")
    db.session.add(run)
    db.session.commit()

    app = current_app._get_current_object()
    threading.Thread(
        target=generate_backlog,
        args=(app, run.run_id, assessment_id, context),
        daemon=True,
    ).start()
    return jsonify(run.to_dict()), 202


@api.get("/assessments/<assessment_id>/backlog")
def get_backlog(assessment_id: str):
    """Latest backlog run (with its tasks) for the frontend to poll."""
    run = _latest_backlog_run(_valid_id(assessment_id))
    if run is None:
        return jsonify({"run": None})

    # Reconcile a run that never finished (no Job to ask - use elapsed time).
    if run.status in ("queued", "running"):
        age = (datetime.now(timezone.utc) - run.started_at).total_seconds()
        if age > _BACKLOG_STALE_SECONDS:
            run.status = "failed"
            run.error = "Backlog generation timed out"
            run.finished_at = db.func.now()
            db.session.commit()
    return jsonify({"run": run.to_dict()})


# -- architecture documents ----------------------------------------------

# Cap per file so a single upload can't exhaust the Volume PUT or memory. The
# whole file is read into memory (Flask default) before it goes to the Volume.
_MAX_DOCUMENT_BYTES = 25 * 1024 * 1024  # 25 MB


@api.get("/assessments/<assessment_id>/documents")
def list_documents(assessment_id: str):
    """Architecture documents attached to an assessment (metadata only), plus
    whether uploading is available in this environment."""
    assessment = db.session.get(Assessment, _valid_id(assessment_id))
    if assessment is None:
        abort(404, description="Assessment not found")
    rows = (
        db.session.execute(
            db.select(ArchitectureDocument)
            .where(ArchitectureDocument.assessment_id == assessment_id)
            .order_by(ArchitectureDocument.uploaded_at.desc())
        )
        .scalars()
        .all()
    )
    return jsonify(
        {
            "enabled": volumes.documents_enabled(),
            "documents": [d.to_dict() for d in rows],
        }
    )


@api.post("/assessments/<assessment_id>/documents")
def upload_document(assessment_id: str):
    """Store one uploaded file in the Volume and record its metadata. Text
    formats are extracted to text now so the agents don't re-parse them; images
    are stored as-is and sent to the model as vision blocks at run time."""
    assessment = db.session.get(Assessment, _valid_id(assessment_id))
    if assessment is None:
        abort(404, description="Assessment not found")
    if not volumes.documents_enabled():
        # No Volume configured (e.g. local dev without a profile). Match the
        # agents' behaviour: report unavailable rather than error.
        return jsonify({"enabled": False}), 202

    file = request.files.get("file")
    if file is None or not file.filename:
        abort(400, description="No file provided")
    filename = file.filename
    if not extract.is_allowed(filename):
        abort(400, description="Unsupported file type")

    data = file.read()
    if not data:
        abort(400, description="Empty file")
    if len(data) > _MAX_DOCUMENT_BYTES:
        abort(413, description="File is larger than 25 MB")

    doc = ArchitectureDocument(
        assessment_id=assessment_id,
        filename=filename,
        content_type=file.mimetype or "application/octet-stream",
        kind=extract.kind_for(filename),
        size=len(data),
        volume_path="",  # filled in below, once the row has an id
    )
    db.session.add(doc)
    db.session.flush()  # assign doc.id before deriving its Volume path

    ext = os.path.splitext(filename)[1].lower()
    doc.volume_path = volumes.document_path(assessment_id, doc.id, ext)
    if doc.kind == "text":
        doc.extracted_text = extract.extract_text(filename, data) or None

    try:
        volumes.upload(doc.volume_path, data)
    except Exception:
        db.session.rollback()
        # Log the underlying cause (surfaced by volumes.upload) so it shows up in
        # `databricks apps logs`; the client only sees the generic 502.
        current_app.logger.exception(
            "Failed to store document %s at %s", filename, doc.volume_path
        )
        abort(502, description="Could not store the file")

    db.session.commit()
    return jsonify(doc.to_dict()), 201


@api.get("/assessments/<assessment_id>/documents/<doc_id>/content")
def download_document(assessment_id: str, doc_id: str):
    """Stream a stored document back for preview/download in the UI."""
    doc = db.session.get(ArchitectureDocument, _valid_id(doc_id))
    if doc is None or doc.assessment_id != _valid_id(assessment_id):
        abort(404, description="Document not found")
    try:
        data = volumes.download(doc.volume_path)
    except Exception:
        abort(502, description="Could not read the file")
    return Response(
        data,
        mimetype=doc.content_type,
        headers={"Content-Disposition": f'inline; filename="{doc.filename}"'},
    )


@api.delete("/assessments/<assessment_id>/documents/<doc_id>")
def delete_document(assessment_id: str, doc_id: str):
    doc = db.session.get(ArchitectureDocument, _valid_id(doc_id))
    if doc is not None and doc.assessment_id == _valid_id(assessment_id):
        volumes.delete(doc.volume_path)  # best-effort; row goes regardless
        db.session.delete(doc)
        db.session.commit()
    return "", 204


# -- static site ---------------------------------------------------------

@site.get("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@site.get("/", defaults={"path": ""})
@site.get("/<path:path>")
def serve_static(path: str):
    static_dir = current_app.config["STATIC_DIR"]
    candidate = os.path.normpath(os.path.join(static_dir, path))
    # Serve a real file inside static_dir; otherwise fall back to index.html so
    # the SPA survives refresh / deep links.
    if path and candidate.startswith(static_dir) and os.path.isfile(candidate):
        return send_from_directory(static_dir, path)
    return send_from_directory(static_dir, "index.html")
