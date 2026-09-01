from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.ml.checks.pe_hardware_matching import MlHardwareMatchingCheck

_Q = Question(
    id="ML-PE-01",
    pillar_id="performance-efficiency",
    title="Match hardware to the ML workload",
    principle="Design workloads for performance",
)

_BILLING_ROWS = [{"total_dbus": 200.0, "gpu_dbus": 60.0}]
_CLUSTER_ROWS = [
    {"node_type_id": "g4dn.xlarge", "cluster_count": 3},
    {"node_type_id": "i3.2xlarge", "cluster_count": 7},
]


def _ctx(*, billing_rows=None, cluster_rows=None, llm_response: str | None = "") -> AgentContext:
    responses = {
        # "gpu_dbus" appears as a column alias in _BILLING_SQL
        "gpu_dbus": billing_rows if billing_rows is not None else _BILLING_ROWS,
        "node_type_id": cluster_rows if cluster_rows is not None else _CLUSTER_ROWS,
    }
    return AgentContext(
        assessment_id="test-ml-pe01",
        layer="ml",
        sql=FakeSqlClient(responses),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_gpu_billing_summary():
    ev = MlHardwareMatchingCheck().collect(_ctx())
    assert ev[0].kind == "sql"
    assert "30.0%" in ev[0].summary  # 60/200


def test_collect_cluster_node_types_summary():
    ev = MlHardwareMatchingCheck().collect(_ctx())
    assert ev[1].kind == "sql"
    # g4dn contains "GPU" keyword match -> 3 GPU-class clusters, 10 total
    assert "3" in ev[1].summary
    assert "GPU" in ev[1].summary


def test_collect_attaches_limitation_note():
    ev = MlHardwareMatchingCheck().collect(_ctx())
    assert ev[2].kind == "note"
    assert "workload" in ev[2].summary


def test_collect_no_billing_data():
    ev = MlHardwareMatchingCheck().collect(_ctx(billing_rows=[]))
    assert "No compute billing" in ev[0].summary


def test_judge_met_verdict():
    resp = (
        '{"verdict": "met", "confidence": "medium", "score": null,'
        ' "rationale": "GPU usage confirmed"}'
    )
    f = MlHardwareMatchingCheck().run(_Q, _ctx(llm_response=resp))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_caps_high_confidence():
    resp = '{"verdict": "partial", "confidence": "high", "score": null, "rationale": "Some GPU"}'
    f = MlHardwareMatchingCheck().run(_Q, _ctx(llm_response=resp))
    assert f.confidence is Confidence.MEDIUM


def test_no_llm_degrades_to_unassessed():
    f = MlHardwareMatchingCheck().run(_Q, _ctx(llm_response=None))
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
