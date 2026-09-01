from __future__ import annotations

from waf_agents.analytics.checks.scp_column_masking import ColumnMaskingCheck
from waf_agents.core.clients import AgentContext, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict

_Q = Question(
    id="ANA-SCP-03",
    pillar_id="security-compliance-privacy",
    title="Mask sensitive fields in analytics outputs",
    principle="Meet compliance and data privacy requirements",
)

# Needles are distinct, non-overlapping substrings of the two SQL strings:
#   "column_masks"   -> _MASKED_SQL (FROM system.information_schema.column_masks)
#   "AS total_columns" -> _TOTAL_SQL  (SELECT COUNT(*) AS total_columns)


def _ctx(masked: int, total: int) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="analytics",
        sql=FakeSqlClient(
            {
                "column_masks": [{"masked_columns": masked}],
                "AS total_columns": [{"total_columns": total}],
            }
        ),
    )


def test_met_ten_percent_masked():
    # 10/100 = 0.10 -> exactly at met threshold
    f = ColumnMaskingCheck().run(_Q, _ctx(10, 100))
    assert f.verdict is Verdict.MET
    assert f.confidence is Confidence.HIGH
    assert f.score == 0.1


def test_met_above_threshold():
    # 50/100 = 0.50 -> met
    f = ColumnMaskingCheck().run(_Q, _ctx(50, 100))
    assert f.verdict is Verdict.MET


def test_partial():
    # 3/100 = 0.03 -> partial
    f = ColumnMaskingCheck().run(_Q, _ctx(3, 100))
    assert f.verdict is Verdict.PARTIAL
    assert f.confidence is Confidence.HIGH


def test_not_met_below_partial_threshold():
    # 1/100 = 0.01 -> not_met
    f = ColumnMaskingCheck().run(_Q, _ctx(1, 100))
    assert f.verdict is Verdict.NOT_MET
    assert f.score == 0.01


def test_not_met_zero_masked():
    f = ColumnMaskingCheck().run(_Q, _ctx(0, 200))
    assert f.verdict is Verdict.NOT_MET
    assert f.score == 0.0


def test_empty_total_is_unknown_low():
    f = ColumnMaskingCheck().run(_Q, _ctx(0, 0))
    assert f.verdict is Verdict.UNKNOWN
    assert f.confidence is Confidence.LOW


def test_collect_evidence_kinds():
    ev = ColumnMaskingCheck().collect(
        AgentContext(
            assessment_id="a1",
            layer="analytics",
            sql=FakeSqlClient(
                {
                    "column_masks": [{"masked_columns": 5}],
                    "AS total_columns": [{"total_columns": 50}],
                }
            ),
        )
    )
    assert ev[0].kind == "sql"
    assert ev[1].kind == "sql"
    assert any(r.get("masked_columns") == 5 for r in ev[0].rows)
    assert any(r.get("total_columns") == 50 for r in ev[1].rows)


def test_score_rounded_to_four_decimal_places():
    # 7/300 = 0.023333... -> rounds to 0.0233
    f = ColumnMaskingCheck().run(_Q, _ctx(7, 300))
    assert f.score is not None
    assert len(str(f.score).replace("0.", "").lstrip("0") or "0") <= 4
