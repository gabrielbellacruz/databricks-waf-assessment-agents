"""Certified and cataloged datasets check (deterministic).

Answers:
  ANA-DG-01  Serve analytics from certified, cataloged datasets

Signal: the share of managed/external tables in Unity Catalog that carry a
certification signal — either a tag with a certified/gold/quality/trusted name
or value, or placement in a schema whose name suggests a curated analytics layer
(gold, serving, mart, curated, certified).  The union of both signals relative to
all UC managed/external tables drives the verdict.
Deterministic ratio vs a threshold -> High confidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.20
_PARTIAL_THRESHOLD = 0.05

_UC_TABLE_COUNT_SQL = (
    "SELECT COUNT(*) AS total_uc_tables"
    " FROM system.information_schema.tables"
    " WHERE table_type IN ('MANAGED','EXTERNAL')"
    " AND table_catalog <> 'hive_metastore'"
)

# UNION deduplicates tables certified via tag OR curated-layer schema name.
_CERTIFIED_SIGNAL_SQL = (
    "SELECT COUNT(DISTINCT fqn) AS certified_tables"
    " FROM ("
    "   SELECT catalog_name || '.' || schema_name || '.' || table_name AS fqn"
    "   FROM system.information_schema.table_tags"
    "   WHERE LOWER(tag_name) IN ('certified','quality','gold','verified','trusted')"
    "      OR LOWER(tag_value) IN ('certified','gold','true','verified','trusted')"
    "   UNION"
    "   SELECT table_catalog || '.' || table_schema || '.' || table_name"
    "   FROM system.information_schema.tables"
    "   WHERE table_catalog <> 'hive_metastore'"
    "   AND table_type IN ('MANAGED','EXTERNAL')"
    "   AND (LOWER(table_schema) LIKE '%gold%'"
    "     OR LOWER(table_schema) LIKE '%serving%'"
    "     OR LOWER(table_schema) LIKE '%mart%'"
    "     OR LOWER(table_schema) LIKE '%curated%'"
    "     OR LOWER(table_schema) LIKE '%certified%')"
    " ) t"
)

_REF = "https://docs.databricks.com/en/data-governance/unity-catalog/tags.html"


@register(layer="analytics", question_ids=["ANA-DG-01"])
class CertifiedDatasetsCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        total_rows = ctx.sql.query(_UC_TABLE_COUNT_SQL)
        cert_rows = ctx.sql.query(_CERTIFIED_SIGNAL_SQL)

        total = int((total_rows[0].get("total_uc_tables") or 0) if total_rows else 0)
        certified = int((cert_rows[0].get("certified_tables") or 0) if cert_rows else 0)

        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{certified} of {total} UC managed/external tables carry a certification"
                    " signal (certified/gold/quality tag or curated-layer schema name)"
                ),
                detail=_UC_TABLE_COUNT_SQL,
                rows=[{"total_uc_tables": total, "certified_tables": certified}],
                ref=_REF,
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total = row["total_uc_tables"]
        certified = row["certified_tables"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No managed or external UC tables found;"
                    " cannot evaluate certification coverage."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        ratio = certified / total
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
                f"{certified} of {total} UC tables ({ratio:.0%}) carry a certification signal"
                f" (certified/gold tag or curated-layer schema);"
                f" threshold for 'met' is {_MET_THRESHOLD:.0%}."
            ),
            sources=evidence,
        )
