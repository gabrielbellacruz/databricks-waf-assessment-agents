"""ACID-supporting storage format check (deterministic).

Answers:
  STO-R-01  Use a storage format that supports ACID transactions

Signal: share of managed/external tables (outside hive_metastore) whose
``data_source_format`` is one of ``('DELTA', 'ICEBERG')`` — formats that
provide full ACID transaction semantics — from
``system.information_schema.tables``.
Deterministic ratio vs a threshold -> High confidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_ACID_FORMATS = ("DELTA", "ICEBERG")
_MET_THRESHOLD = 0.90
_PARTIAL_THRESHOLD = 0.60


def _catalog_filter(catalogs: list[str]) -> str:
    if not catalogs:
        return ""
    quoted = ", ".join("'" + c.replace("'", "''") + "'" for c in catalogs)
    return f"AND table_catalog IN ({quoted})"


@register(layer="storage", question_ids=["STO-R-01"])
class AcidFormatCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        catalogs = ctx.scope.catalogs if ctx.scope else ctx.catalogs
        acid_list = ", ".join(f"'{f}'" for f in _ACID_FORMATS)
        sql = (
            "SELECT COUNT(*) AS total, "
            f"SUM(CASE WHEN data_source_format IN ({acid_list}) THEN 1 ELSE 0 END) AS acid_count "
            "FROM system.information_schema.tables "
            "WHERE table_type IN ('MANAGED', 'EXTERNAL') "
            "AND table_catalog <> 'hive_metastore' "
            f"{_catalog_filter(catalogs)}"
        ).strip()
        rows = ctx.sql.query(sql)
        row = rows[0] if rows else {"total": 0, "acid_count": 0}
        total = int(row.get("total") or 0)
        acid_count = int(row.get("acid_count") or 0)
        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{acid_count} of {total} managed/external tables use an ACID-supporting "
                    "format (Delta/Iceberg)"
                ),
                detail=sql,
                rows=[{"total": total, "acid_count": acid_count}],
                ref="https://docs.databricks.com/en/delta/acid-transactions.html",
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total = row["total"]
        acid_count = row["acid_count"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No managed or external tables found in scope to evaluate ACID format adoption."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        ratio = acid_count / total
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
                f"{acid_count} of {total} tables ({ratio:.0%}) use an ACID-supporting format "
                f"(Delta or Iceberg); threshold for 'met' is {_MET_THRESHOLD:.0%}."
            ),
            sources=evidence,
        )
