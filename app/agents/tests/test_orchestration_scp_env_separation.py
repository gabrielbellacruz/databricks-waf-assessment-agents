from __future__ import annotations

from waf_agents.core.clients import AgentContext, FakeLlmClient, FakeSqlClient
from waf_agents.core.models import Confidence, Question, Verdict
from waf_agents.orchestration.checks.scp_env_separation import EnvSeparationCheck

_Q = Question(
    id="ORC-SCP-05",
    pillar_id="scp",
    title="Separate credentials across environments",
    principle="Use distinct service principals and secret scopes for prod and non-prod workflows",
)

# Two distinct needles for the two SQL queries
# _SQL_MIXED_IDS groups by run_as; _SQL_ENV_COUNTS does not.
_MIXED_IDS_NEEDLE = "GROUP BY run_as"
_ENV_COUNTS_NEEDLE = "prod_named_jobs"


def _mixed_row(run_as: str, total: int, prod: int, non_prod: int) -> dict:
    return {"run_as": run_as, "total_jobs": total, "prod_jobs": prod, "non_prod_jobs": non_prod}


def _ctx(
    mixed_rows: list[dict],
    total: int,
    prod_named: int,
    non_prod_named: int,
    llm_response: str | None = "",
) -> AgentContext:
    return AgentContext(
        assessment_id="a1",
        layer="orchestration",
        sql=FakeSqlClient(
            {
                _MIXED_IDS_NEEDLE: mixed_rows,
                _ENV_COUNTS_NEEDLE: [
                    {
                        "total_jobs": total,
                        "prod_named_jobs": prod_named,
                        "non_prod_named_jobs": non_prod_named,
                    }
                ],
            }
        ),
        llm=FakeLlmClient(llm_response) if llm_response is not None else None,
    )


def test_collect_returns_three_evidence_pieces():
    ev = EnvSeparationCheck().collect(
        _ctx(
            [_mixed_row("sp-shared", 10, 5, 5)],
            total=20,
            prod_named=8,
            non_prod_named=7,
        )
    )
    assert len(ev) == 3
    assert ev[0].kind == "sql"
    assert ev[1].kind == "sql"
    assert ev[2].kind == "note"


def test_collect_identifies_mixed_identities():
    # One SP spans both prod and non-prod → risk
    ev = EnvSeparationCheck().collect(
        _ctx(
            [
                _mixed_row("sp-shared", 10, 5, 5),  # mixed -> risk
                _mixed_row("sp-prod-only", 5, 5, 0),  # not mixed
            ],
            total=30,
            prod_named=10,
            non_prod_named=8,
        )
    )
    assert "1 run_as identities span both" in ev[0].summary


def test_collect_no_env_named_jobs():
    ev = EnvSeparationCheck().collect(_ctx([], total=10, prod_named=0, non_prod_named=0))
    assert "cannot assess" in ev[0].summary.lower()


def test_collect_env_coverage_summary():
    ev = EnvSeparationCheck().collect(
        _ctx([], total=50, prod_named=20, non_prod_named=15)
    )
    assert "20 prod-named" in ev[1].summary
    assert "15 non-prod-named" in ev[1].summary


def test_judge_not_met_mixed_credentials():
    resp = (
        '{"verdict": "not_met", "confidence": "medium",'
        ' "score": null, "rationale": "Shared SP found across prod and dev environments"}'
    )
    f = EnvSeparationCheck().run(
        _Q,
        _ctx(
            [_mixed_row("sp-shared", 8, 4, 4)],
            total=20,
            prod_named=8,
            non_prod_named=6,
            llm_response=resp,
        ),
    )
    assert f.verdict is Verdict.NOT_MET
    assert f.confidence is Confidence.MEDIUM


def test_judge_met_separated_credentials():
    resp = (
        '{"verdict": "met", "confidence": "medium",'
        ' "score": null, "rationale": "No shared SPs across prod and non-prod"}'
    )
    f = EnvSeparationCheck().run(
        _Q,
        _ctx([], total=30, prod_named=15, non_prod_named=12, llm_response=resp),
    )
    assert f.verdict is Verdict.MET


def test_no_llm_degrades_to_unassessed():
    f = EnvSeparationCheck().run(
        _Q,
        _ctx(
            [_mixed_row("sp-shared", 5, 3, 2)],
            total=15,
            prod_named=6,
            non_prod_named=5,
            llm_response=None,
        ),
    )
    assert f.verdict is Verdict.UNKNOWN
    assert f.auto_assessable is False
    assert f.sources
