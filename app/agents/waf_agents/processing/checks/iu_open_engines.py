"""Open standard processing engines check (deterministic).

Answers:
  PRO-IU-02  Use open, standard processing engines

Signal: the share of managed/external Unity Catalog tables stored in an
open format (Delta / Iceberg / Delta Sharing) from
``system.information_schema.tables``.  Open-format table outputs are the
primary observable proxy for whether transformation pipelines write to
open, standard formats — the expected output of open processing engines
such as Apache Spark and Databricks Delta Engine.
Deterministic ratio vs a threshold -> High confidence.
Denominator 0 -> UNKNOWN/LOW.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_OPEN_FORMATS = ("DELTA", "ICEBERG", "DELTASHARING")
_MET_THRESHOLD = 0.80
_PARTIAL_THRESHOLD = 0.50

_REF = "https://docs.databricks.com/en/delta/index.html"


@register(layer="processing", question_ids=["PRO-IU-02"])
class ProcessingOpenEnginesCheck(Check):
    """Assess open-engine adoption via open-format table output coverage.

    Queries ``system.information_schema.tables`` for the ratio of
    managed/external UC tables using Delta, Iceberg, or Delta Sharing.
    A high share indicates that transformation pipelines write to open,
    interoperable formats — the expected output of Databricks-native and
    Apache Spark-based processing engines.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        open_list = ", ".join(f"'{f}'" for f in _OPEN_FORMATS)
        sql = (
            "SELECT COUNT(*) AS total, "
            f"SUM(CASE WHEN data_source_format IN ({open_list}) THEN 1 ELSE 0 END) AS open_fmt "
            "FROM system.information_schema.tables "
            "WHERE table_type IN ('MANAGED', 'EXTERNAL') "
            "AND table_catalog <> 'hive_metastore'"
        )
        rows = ctx.sql.query(sql)
        row = rows[0] if rows else {"total": 0, "open_fmt": 0}
        total = int(row.get("total") or 0)
        open_fmt = int(row.get("open_fmt") or 0)
        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{open_fmt} of {total} managed/external UC tables "
                    "use an open format (Delta/Iceberg/Delta Sharing)"
                ),
                detail=sql,
                rows=[{"total": total, "open_fmt": open_fmt}],
                ref=_REF,
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total = row["total"]
        open_fmt = row["open_fmt"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No managed or external UC tables found; "
                    "cannot assess open-format output coverage."
                ),
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
                f"{open_fmt} of {total} managed/external UC tables ({ratio:.0%}) "
                f"use an open format (Delta/Iceberg/Delta Sharing); "
                f"threshold for 'met' is {_MET_THRESHOLD:.0%}."
            ),
            sources=evidence,
        )
