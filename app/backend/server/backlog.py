"""Results-level backlog agent: turn an assessment's results into a prioritized
implementation backlog by prompting a Claude serving endpoint.

Unlike the per-layer agents (Databricks Jobs that scan the workspace), this needs
no workspace access - only the assessment's own results, which the frontend sends
in the request and which the app enriches with the latest agent findings from its
own DB. So it runs in a background thread inside the app and calls the model over
REST.

Stdlib-only for the HTTP/auth path (urllib + server.config), like server.agents:
the Databricks Apps build proxy is flaky, so the app must not depend on
databricks-sdk. DB access uses the app's existing SQLAlchemy session.
"""

import json
import os
import urllib.request
from datetime import datetime, timezone

from server.config import IS_DATABRICKS_APP, _host, _sp_oauth_token
from server.db import db
from server.models import AgentFinding, AgentRun, BacklogRun

# Layers whose latest agent findings enrich the prompt (mirrors routes._AGENT_LAYERS).
_LAYERS = (
    "ingestion",
    "storage",
    "processing",
    "orchestration",
    "analytics",
    "ai",
    "ml",
)

_SEVERITIES = {"high", "medium", "low"}
# Statuses that count as "done" for a question, so the rest are gaps to plan for.
_DONE_STATUSES = {"completed", "ignore"}
# Agent verdicts that flag a gap even when a human hasn't answered.
_GAP_VERDICTS = {"partial", "not_met"}
# Bound the prompt so a very large assessment can't blow the context window.
_MAX_GAPS = 200

_SYSTEM_PROMPT = (
    "You are a Databricks Well-Architected Framework delivery lead. You are given a "
    "customer's WAF assessment results: overall and per-layer/per-pillar scores and, "
    "for the questions that are not yet satisfied, their status, the reviewer's notes, "
    "and (when available) an automated agent's verdict and rationale.\n\n"
    "Produce a prioritized implementation backlog of concrete tasks the customer should "
    "carry out to close the gaps. Prioritize by risk: security, governance, and "
    "reliability gaps come first, then cost and performance. Weigh implementation "
    "complexity and sequence dependencies (foundational work before what builds on it). "
    "Keep tasks concrete and actionable; merge closely related gaps into one task rather "
    "than emitting one task per question. Aim for the ~10-20 highest-leverage tasks.\n\n"
    "Fields per task:\n"
    "  title       - short imperative summary\n"
    "  description - what to do and why it matters, 1-3 sentences\n"
    "  pillar      - the WAF pillar it belongs to\n"
    "  layer       - the architecture layer it belongs to (or 'Cross-cutting')\n"
    "  criticality - high | medium | low (business/risk urgency)\n"
    "  complexity  - high | medium | low (implementation effort)\n"
    "  timeline    - a rough duration estimate, e.g. '1-2 weeks', '1 quarter'\n"
    "  priority    - integer rank, 1 = do first (unique, contiguous)\n"
    "  dependsOn   - list of other task titles that must come first (may be empty)\n\n"
    "Respond with ONLY a JSON object, no prose and no code fences:\n"
    '{"tasks": [{"title": "...", "description": "...", "pillar": "...", "layer": "...", '
    '"criticality": "high|medium|low", "complexity": "high|medium|low", '
    '"timeline": "...", "priority": 1, "dependsOn": []}]}'
)


def _model() -> str:
    """The serving endpoint to prompt. Same default as the layer agents."""
    return os.environ.get("WAF_ASSESSMENT_MODEL", "databricks-claude-opus-4-8")


def backlog_enabled() -> bool:
    """True when the app can mint an SP token to call the model. No-op locally,
    like the layer agents, so the app still works without a workspace."""
    return IS_DATABRICKS_APP


def latest_findings(assessment_id: str) -> dict[str, dict]:
    """Latest agent verdict + rationale per question id, across all layers.

    For each layer takes the most recent run and its findings; layers with no run
    simply contribute nothing. Best-effort context, not required."""
    out: dict[str, dict] = {}
    for layer in _LAYERS:
        run = db.session.execute(
            db.select(AgentRun)
            .where(AgentRun.assessment_id == assessment_id, AgentRun.layer == layer)
            .order_by(AgentRun.started_at.desc())
        ).scalar()
        if run is None:
            continue
        rows = (
            db.session.execute(
                db.select(AgentFinding).where(AgentFinding.run_id == run.run_id)
            )
            .scalars()
            .all()
        )
        for f in rows:
            out[f.question_id] = {"verdict": f.verdict, "rationale": f.rationale}
    return out


def _clip(value: object, limit: int) -> str:
    text = str(value or "").strip().replace("\n", " ")
    return text[:limit]


def build_prompt(context: dict, findings_by_qid: dict[str, dict]) -> tuple[str, str]:
    """Build (system, user) messages from the posted results context.

    The user message summarizes scores and lists the gap questions (not completed
    / ignored, or flagged partial/not_met by an agent) compactly."""
    lines: list[str] = []
    name = _clip(context.get("assessmentName"), 200) or "Untitled assessment"
    cloud = _clip(context.get("cloudProvider"), 40) or "not specified"
    lines.append(f"ASSESSMENT: {name}")
    lines.append(f"Cloud provider: {cloud}")

    overall = context.get("overall") or {}
    lines.append(
        "Overall score {sp}% ({ts}/{ms} points); {aq}/{tq} questions answered "
        "({cp}% complete).".format(
            sp=overall.get("scorePercentage", 0),
            ts=overall.get("totalScore", 0),
            ms=overall.get("maxPossibleScore", 0),
            aq=overall.get("answeredQuestions", 0),
            tq=overall.get("totalQuestions", 0),
            cp=overall.get("completionPercentage", 0),
        )
    )

    layers = context.get("layers") or []
    if layers:
        lines.append("\nSCORES BY LAYER / PILLAR:")
        for layer in layers:
            lname = _clip(layer.get("name"), 60)
            lines.append(f"- {lname}: {layer.get('scorePercentage', 0)}%")
            for pillar in layer.get("pillars") or []:
                pname = _clip(pillar.get("name"), 60)
                lines.append(f"    - {pname}: {pillar.get('scorePercentage', 0)}%")

    gaps: list[str] = []
    completed = 0
    for layer in layers:
        lname = _clip(layer.get("name"), 60)
        for pillar in layer.get("pillars") or []:
            pname = _clip(pillar.get("name"), 60)
            for q in pillar.get("questions") or []:
                status = str(q.get("status") or "")
                finding = findings_by_qid.get(str(q.get("id")))
                verdict = finding.get("verdict") if finding else None
                is_gap = status not in _DONE_STATUSES or verdict in _GAP_VERDICTS
                if not is_gap:
                    completed += 1
                    continue
                if len(gaps) >= _MAX_GAPS:
                    continue
                parts = [
                    f"[{_clip(q.get('identifier'), 20)}] ({lname} / {pname})",
                    f"status={status or 'unanswered'}",
                ]
                if verdict:
                    parts.append(f"agent={verdict}")
                parts.append(f"title={_clip(q.get('title'), 160)}")
                note = _clip(q.get("note"), 300)
                if note:
                    parts.append(f"note={note}")
                if finding and finding.get("rationale"):
                    parts.append(f"agent_rationale={_clip(finding.get('rationale'), 200)}")
                gaps.append("- " + "; ".join(parts))

    lines.append(f"\nCOMPLETED/IGNORED QUESTIONS: {completed}")
    lines.append(f"\nGAP QUESTIONS ({len(gaps)}):")
    lines.extend(gaps if gaps else ["(none - the assessment has no open gaps)"])

    return _SYSTEM_PROMPT, "\n".join(lines)


def _parse_json(text: str) -> dict | None:
    """Tolerant JSON-object extraction (mirrors agents' llm._parse): strips code
    fences and takes the outermost {...}."""
    s = (text or "").strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        if s.lstrip().startswith("json"):
            s = s.lstrip()[4:]
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        obj = json.loads(s[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def _severity(value: object) -> str:
    v = str(value or "").strip().lower()
    return v if v in _SEVERITIES else "medium"


def parse_tasks(reply: str) -> list[dict]:
    """Extract and normalize the task list from the model reply. Malformed tasks
    are dropped; the result is sorted by priority. Returns [] on unparseable input."""
    parsed = _parse_json(reply)
    if parsed is None:
        return []
    raw = parsed.get("tasks")
    if not isinstance(raw, list):
        return []

    tasks: list[dict] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        title = _clip(item.get("title"), 200)
        if not title:
            continue
        priority = item.get("priority")
        if not isinstance(priority, int) or isinstance(priority, bool):
            try:
                priority = int(priority)
            except (TypeError, ValueError):
                priority = i + 1
        depends = item.get("dependsOn")
        depends_on = (
            [_clip(d, 200) for d in depends if str(d or "").strip()]
            if isinstance(depends, list)
            else []
        )
        tasks.append(
            {
                "title": title,
                "description": _clip(item.get("description"), 1000),
                "pillar": _clip(item.get("pillar"), 80),
                "layer": _clip(item.get("layer"), 80),
                "criticality": _severity(item.get("criticality")),
                "complexity": _severity(item.get("complexity")),
                "timeline": _clip(item.get("timeline"), 80),
                "priority": priority,
                "dependsOn": depends_on,
            }
        )

    tasks.sort(key=lambda t: t["priority"])
    return tasks


def generate_backlog(app, run_id: str, assessment_id: str, context: dict) -> None:
    """Background worker: prompt the model and persist the backlog on the run row.

    Runs in its own thread with a fresh app context + session, so any gunicorn
    worker can serve the poll that reads the result back."""
    with app.app_context():
        try:
            run = db.session.get(BacklogRun, run_id)
            if run is None:
                return
            run.status = "running"
            run.model = _model()
            db.session.commit()

            system, user = build_prompt(context or {}, latest_findings(assessment_id))
            tasks = parse_tasks(_call_model(system, user))

            run = db.session.get(BacklogRun, run_id)
            if run is not None:
                run.status = "done"
                run.tasks = tasks
                run.finished_at = datetime.now(timezone.utc)
                db.session.commit()
        except Exception as exc:  # noqa: BLE001 - record any failure for the UI
            db.session.rollback()
            run = db.session.get(BacklogRun, run_id)
            if run is not None:
                run.status = "failed"
                run.error = str(exc)[:2000]
                run.finished_at = datetime.now(timezone.utc)
                db.session.commit()
        finally:
            db.session.remove()


def _call_model(system: str, user: str) -> str:
    """Query the model serving endpoint over REST and return the message text."""
    url = f"{_host()}/serving-endpoints/{_model()}/invocations"
    body = json.dumps(
        {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": 4000,
        }
    ).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {_sp_oauth_token()}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.load(resp)
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return message.get("content") or ""
