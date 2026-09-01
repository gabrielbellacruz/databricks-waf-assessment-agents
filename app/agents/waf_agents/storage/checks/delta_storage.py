"""Delta Lake storage check (deterministic).

Answers:
  STO-IU-01  Store data in Delta Lake

Signal: share of managed/external tables (outside hive_metastore) whose
``data_source_format`` is ``'DELTA'``, from ``system.information_schema.tables``.
Deterministic ratio vs a threshold -> High confidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.90
_PARTIAL_THRESHOLD = 0.60


def _catalog_filter(catalogs: list[str]) -> str:
    if not catalogs:
        return ""
    quoted = ", ".join("'" + c.replace("'", "''") + "'" for c in catalogs)
    return f"AND table_catalog IN ({quoted})"


@register(layer="storage", question_ids=["STO-IU-01"])
class DeltaStorageCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        catalogs = ctx.scope.catalogs if ctx.scope else ctx.catalogs
        sql = (
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN data_source_format = 'DELTA' THEN 1 ELSE 0 END) AS delta_count "
            "FROM system.information_schema.tables "
            "WHERE table_type IN ('MANAGED', 'EXTERNAL') "
            "AND table_catalog <> 'hive_metastore' "
            f"{_catalog_filter(catalogs)}"
        ).strip()
        rows = ctx.sql.query(sql)
        row = rows[0] if rows else {"total": 0, "delta_count": 0}
        total = int(row.get("total") or 0)
        delta_count = int(row.get("delta_count") or 0)
        return [
            Evidence(
                kind="sql",
                summary=f"{delta_count} of {total} managed/external tables use Delta Lake format",
                detail=sql,
                rows=[{"total": total, "delta_count": delta_count}],
                ref="https://docs.databricks.com/en/delta/index.html",
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total = row["total"]
        delta_count = row["delta_count"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No managed or external tables found in scope to evaluate "
                    "Delta Lake adoption."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        ratio = delta_count / total
        if ratio >= _MET_THRESHOLD:
            verdict = Verdict.MET
        elif ratio >= _PARTIAL_THRESHOLD:
            verdict = Verdict.PARTIAL
        else:
            verdict = Verdict.NOT_MET

        return Finding(
            question_id=question.id,
            pillar_id=question.pillar_id,
            verdict=verdict,
            confidence=Confidence.HIGH,
            score=round(ratio, 4),
            rationale=(
                f"{delta_count} of {total} tables ({ratio:.0%}) use Delta Lake format; "
                f"threshold for 'met' is {_MET_THRESHOLD:.0%}."
            ),
            sources=evidence,
        )
