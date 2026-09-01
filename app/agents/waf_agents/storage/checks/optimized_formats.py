"""Performance-optimized storage format check (deterministic).

Answers:
  STO-CO-01  Store data in performance-optimized formats

Signal: share of managed/external tables (outside hive_metastore) whose
``data_source_format`` is one of ``('DELTA', 'ICEBERG', 'PARQUET', 'ORC')`` —
columnar, performance-optimized formats — versus row/text formats
(CSV, JSON, TEXT, AVRO), from ``system.information_schema.tables``.
Deterministic ratio vs a threshold -> High confidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_OPTIMIZED_FORMATS = ("DELTA", "ICEBERG", "PARQUET", "ORC")
_MET_THRESHOLD = 0.80
_PARTIAL_THRESHOLD = 0.50


def _catalog_filter(catalogs: list[str]) -> str:
    if not catalogs:
        return ""
    quoted = ", ".join("'" + c.replace("'", "''") + "'" for c in catalogs)
    return f"AND table_catalog IN ({quoted})"


@register(layer="storage", question_ids=["STO-CO-01"])
class OptimizedFormatsCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        catalogs = ctx.scope.catalogs if ctx.scope else ctx.catalogs
        optimized_list = ", ".join(f"'{f}'" for f in _OPTIMIZED_FORMATS)
        sql = (
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN data_source_format IN "
            f"({optimized_list}) THEN 1 ELSE 0 END) AS optimized_count "
            "FROM system.information_schema.tables "
            "WHERE table_type IN ('MANAGED', 'EXTERNAL') "
            "AND table_catalog <> 'hive_metastore' "
            f"{_catalog_filter(catalogs)}"
        ).strip()
        rows = ctx.sql.query(sql)
        row = rows[0] if rows else {"total": 0, "optimized_count": 0}
        total = int(row.get("total") or 0)
        optimized_count = int(row.get("optimized_count") or 0)
        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{optimized_count} of {total} managed/external tables use a "
                    "performance-optimized columnar format (Delta/Iceberg/Parquet/ORC)"
                ),
                detail=sql,
                rows=[{"total": total, "optimized_count": optimized_count}],
                ref="https://docs.databricks.com/en/delta/optimizations/index.html",
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total = row["total"]
        optimized_count = row["optimized_count"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No managed or external tables found in scope to evaluate "
                    "performance-optimized format adoption."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        ratio = optimized_count / total
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
                f"{optimized_count} of {total} tables ({ratio:.0%}) use a performance-optimized "
                "columnar format (Delta/Iceberg/Parquet/ORC); "
                f"threshold for 'met' is {_MET_THRESHOLD:.0%}."
            ),
            sources=evidence,
        )
