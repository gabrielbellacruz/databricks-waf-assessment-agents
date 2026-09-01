from __future__ import annotations

from waf_agents import create_agent, list_agents
from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Verdict
from waf_agents.core.questions import load_questions
from waf_agents.core.registry import check_for
from waf_agents.ingestion.checks.open_formats import OpenFormatsCheck


def test_registry_maps_questions_to_check():
    assert check_for("ING-IU-03") is OpenFormatsCheck
    assert check_for("ING-CO-05") is OpenFormatsCheck
    assert check_for("does-not-exist") is None


def test_factory_knows_ingestion():
    assert "ingestion" in list_agents()
    assert create_agent("ingestion").layer == "ingestion"


def test_questions_loaded_from_fixture():
    qs = load_questions("ingestion")
    assert {q.id for q in qs} == {"ING-IU-03", "ING-IU-99"}
    assert next(q for q in qs if q.id == "ING-IU-03").checklist  # checklist parsed


def _ctx(responses):
    return AgentContext(
        assessment_id="a1",
        layer="ingestion",
        sql=FakeSqlClient(responses),
        catalogs=["main"],
    )


def test_full_run_produces_verdict_and_defers_unmapped():
    ctx = _ctx({"data_source_format": [{"total": 100, "open_fmt": 90}]})
    findings = {f.question_id: f for f in create_agent("ingestion").run(ctx)}

    # mapped, deterministic High-confidence verdict
    met = findings["ING-IU-03"]
    assert met.verdict is Verdict.MET
    assert met.confidence is Confidence.HIGH
    assert met.score == 0.9
    assert met.sources and met.sources[0].kind == "sql"

    # unmapped question degrades gracefully rather than breaking the run
    deferred = findings["ING-IU-99"]
    assert deferred.verdict is Verdict.UNKNOWN
    assert deferred.auto_assessable is False


def test_open_formats_thresholds():
    q = load_questions("ingestion")[0]
    check = OpenFormatsCheck()

    not_met = check.run(q, _ctx({"data_source_format": [{"total": 100, "open_fmt": 10}]}))
    assert not_met.verdict is Verdict.NOT_MET

    partial = check.run(q, _ctx({"data_source_format": [{"total": 100, "open_fmt": 60}]}))
    assert partial.verdict is Verdict.PARTIAL

    empty = check.run(q, _ctx({"data_source_format": [{"total": 0, "open_fmt": 0}]}))
    assert empty.verdict is Verdict.UNKNOWN
