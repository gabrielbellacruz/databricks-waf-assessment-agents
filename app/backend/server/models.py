"""SQLAlchemy models.

JSON is camelCase to match the frontend `Assessment` type (see frontend/src/types/waf.ts
and frontend/src/store/api.ts); `answers` and `categories` are JSONB. Assessments are
shared org-wide (no per-user scoping).
"""

import uuid

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from server.db import db


def _new_id() -> str:
    return f"assessment-{uuid.uuid4().hex}"


def _new_backlog_id() -> str:
    return f"backlog-{uuid.uuid4().hex}"


class Assessment(db.Model):
    __tablename__ = "assessments"

    id = db.Column(db.Text, primary_key=True, default=_new_id)
    name = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, nullable=False, server_default="")
    categories = db.Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    cloud_provider = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    imported_at = db.Column(db.Text, nullable=True)
    answers = db.Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    # Free-text notes, keyed like answers: categoryId -> pillarId -> questionId -> text.
    notes = db.Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    def to_dict(self) -> dict:
        result = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "categories": self.categories,
            "cloudProvider": self.cloud_provider,
            "createdAt": self.created_at.isoformat(),
            "updatedAt": self.updated_at.isoformat(),
            "answers": self.answers,
            "notes": self.notes,
        }
        if self.imported_at is not None:
            result["importedAt"] = self.imported_at
        return result


class AgentRun(db.Model):
    """One execution of a layer agent for an assessment.

    The app inserts a row (status=queued) when it triggers the agent Job; the
    Job updates status/progress as it runs and writes findings keyed to this
    run. Findings are versioned by run_id so history is retained and the latest
    run wins for display.
    """

    __tablename__ = "agent_runs"

    run_id = db.Column(db.Text, primary_key=True, default=_new_id)
    assessment_id = db.Column(
        db.Text,
        db.ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    layer = db.Column(db.Text, nullable=False)
    # queued -> running -> done | failed
    status = db.Column(db.Text, nullable=False, server_default="queued")
    n_total = db.Column(db.Integer, nullable=False, server_default="0")
    n_done = db.Column(db.Integer, nullable=False, server_default="0")
    error = db.Column(db.Text, nullable=True)
    job_run_id = db.Column(db.Text, nullable=True)  # Databricks Jobs run id
    agent_version = db.Column(db.Text, nullable=True)
    started_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at = db.Column(db.DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict:
        return {
            "runId": self.run_id,
            "assessmentId": self.assessment_id,
            "layer": self.layer,
            "status": self.status,
            "nTotal": self.n_total,
            "nDone": self.n_done,
            "error": self.error,
            "startedAt": self.started_at.isoformat(),
            "finishedAt": self.finished_at.isoformat() if self.finished_at else None,
        }


class AgentFinding(db.Model):
    """The agent's answer for one question within a run.

    ``verdict`` is a compliance judgment (met/partial/not_met/unknown), distinct
    from the workflow ``status`` in ``Assessment.answers``. Findings are a
    read-only side-car in M1; a reviewer accept flow that promotes a verdict into the
    scored answers is designed later.
    """

    __tablename__ = "agent_findings"

    id = db.Column(db.Text, primary_key=True, default=_new_id)
    run_id = db.Column(
        db.Text,
        db.ForeignKey("agent_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assessment_id = db.Column(db.Text, nullable=False, index=True)
    category_id = db.Column(db.Text, nullable=False)
    pillar_id = db.Column(db.Text, nullable=False)
    question_id = db.Column(db.Text, nullable=False)
    verdict = db.Column(db.Text, nullable=False)
    score = db.Column(db.Float, nullable=True)
    confidence = db.Column(db.Text, nullable=False)
    rationale = db.Column(db.Text, nullable=False, server_default="")
    sources = db.Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    auto_assessable = db.Column(db.Boolean, nullable=False, server_default=text("true"))
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        db.UniqueConstraint("run_id", "question_id", name="uq_finding_run_question"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "runId": self.run_id,
            "categoryId": self.category_id,
            "pillarId": self.pillar_id,
            "questionId": self.question_id,
            "verdict": self.verdict,
            "score": self.score,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "sources": self.sources,
            "autoAssessable": self.auto_assessable,
            "createdAt": self.created_at.isoformat(),
        }


class BacklogRun(db.Model):
    """One on-demand run of the results-level backlog agent for an assessment.

    Unlike the per-layer AgentRun (a Databricks Job that scans the workspace),
    this reasons over the assessment's own results and runs in a background
    thread inside the app; there is no Job, so ``job_run_id`` has no analogue and
    a stuck run is reconciled by elapsed time instead of the Jobs API. The
    generated tasks are stored as JSONB on the row - they are always read and
    written as a whole set, like ``Assessment.answers``.
    """

    __tablename__ = "backlog_runs"

    run_id = db.Column(db.Text, primary_key=True, default=_new_backlog_id)
    assessment_id = db.Column(
        db.Text,
        db.ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # queued -> running -> done | failed
    status = db.Column(db.Text, nullable=False, server_default="queued")
    error = db.Column(db.Text, nullable=True)
    model = db.Column(db.Text, nullable=True)
    # Prioritized task list produced by the agent (see server/backlog.py).
    tasks = db.Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    started_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at = db.Column(db.DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict:
        return {
            "runId": self.run_id,
            "assessmentId": self.assessment_id,
            "status": self.status,
            "error": self.error,
            "model": self.model,
            "tasks": self.tasks,
            "startedAt": self.started_at.isoformat(),
            "finishedAt": self.finished_at.isoformat() if self.finished_at else None,
        }
