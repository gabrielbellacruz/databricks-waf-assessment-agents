"""Open-format landing check.

Answers:
  ING-IU-03  Land ingested data in open formats
  ING-CO-05  Land data in performance-optimized open formats

Signal: the share of managed/external tables stored in an open format
(Delta / Iceberg / Delta Sharing) from ``system.information_schema.tables``.
Deterministic ratio vs a threshold -> High confidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_OPEN_FORMATS = ("DELTA", "ICEBERG", "DELTASHARING")
_MET_THRESHOLD = 0.80
_PARTIAL_THRESHOLD = 0.50


def _catalog_filter(catalogs: list[str]) -> str:
    if not catalogs:
        return ""
    quoted = ", ".join("'" + c.replace("'", "''") + "'" for c in catalogs)
    return f"AND table_catalog IN ({quoted})"


@register(layer="ingestion", question_ids=["ING-IU-03", "ING-CO-05"])
class OpenFormatsCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        catalogs = ctx.scope.catalogs if ctx.scope else ctx.catalogs
        open_list = ", ".join(f"'{f}'" for f in _OPEN_FORMATS)
        sql = (
            "SELECT COUNT(*) AS total, "
            f"SUM(CASE WHEN data_source_format IN ({open_list}) THEN 1 ELSE 0 END) AS open_fmt "
            "FROM system.information_schema.tables "
            "WHERE table_type IN ('MANAGED', 'EXTERNAL') "
            "AND table_catalog <> 'hive_metastore' "
            f"{_catalog_filter(catalogs)}"
        ).strip()
        rows = ctx.sql.query(sql)
        row = rows[0] if rows else {"total": 0, "open_fmt": 0}
        total = int(row.get("total") or 0)
        open_fmt = int(row.get("open_fmt") or 0)
        return [
            Evidence(
                kind="sql",
                summary=f"{open_fmt} of {total} managed/external tables use an open format",
                detail=sql,
                rows=[{"total": total, "open_fmt": open_fmt}],
                ref="https://docs.databricks.com/en/delta/index.html",
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total, open_fmt = row["total"], row["open_fmt"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale="No managed or external tables found in scope to evaluate.",
                sources=evidence,
                auto_assessable=True,
            )

        ratio = open_fmt / total
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
                f"{open_fmt} of {total} tables ({ratio:.0%}) use an open format "
                f"(Delta/Iceberg/Delta Sharing); threshold for 'met' is {_MET_THRESHOLD:.0%}."
            ),
            sources=evidence,
        )
