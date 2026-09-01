"""Medallion (layered) storage architecture check (deterministic).

Answers:
  STO-OE-04  Use a layered (medallion) storage architecture

Signal: presence of bronze / silver / gold layer families inferred from schema
names in ``system.information_schema.schemata``.  Each family is matched by
regex against the lowercased schema name:

  bronze  — matches: bronze, raw, _brz, landing
  silver  — matches: silver, refined, clean, _slv, staging
  gold    — matches: gold, curated, serving, mart, _gld

Verdict logic:
  MET     — all three families have at least one matching schema
  PARTIAL — one or two families present
  NOT_MET — no family present (but schemas exist)
  UNKNOWN — no schemas found at all

Confidence is MEDIUM because naming is a proxy signal, not a clean count of
actual layer tables; a reviewer should confirm.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_BRONZE_PATTERN = "bronze|raw|_brz|landing"
_SILVER_PATTERN = "silver|refined|clean|_slv|staging"
_GOLD_PATTERN = "gold|curated|serving|mart|_gld"


@register(layer="storage", question_ids=["STO-OE-04"])
class MedallionArchitectureCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        sql = (
            "SELECT COUNT(*) AS total_schemas, "
            f"SUM(CASE WHEN LOWER(schema_name) RLIKE '{_BRONZE_PATTERN}' THEN 1 ELSE 0 END) "
            "AS bronze_count, "
            f"SUM(CASE WHEN LOWER(schema_name) RLIKE '{_SILVER_PATTERN}' THEN 1 ELSE 0 END) "
            "AS silver_count, "
            f"SUM(CASE WHEN LOWER(schema_name) RLIKE '{_GOLD_PATTERN}' THEN 1 ELSE 0 END) "
            "AS gold_count "
            "FROM system.information_schema.schemata "
            "WHERE schema_name <> 'information_schema' "
            "AND catalog_name <> 'hive_metastore'"
        )
        rows = ctx.sql.query(sql)
        row = rows[0] if rows else {
            "total_schemas": 0, "bronze_count": 0, "silver_count": 0, "gold_count": 0
        }
        total_schemas = int(row.get("total_schemas") or 0)
        bronze_count = int(row.get("bronze_count") or 0)
        silver_count = int(row.get("silver_count") or 0)
        gold_count = int(row.get("gold_count") or 0)
        families = sum(1 for c in (bronze_count, silver_count, gold_count) if c > 0)
        return [
            Evidence(
                kind="sql",
                summary=(
                    f"Medallion layer families detected: {families} of 3 "
                    f"(bronze: {bronze_count}, silver: {silver_count}, gold: {gold_count}) "
                    f"across {total_schemas} schema(s)"
                ),
                detail=sql,
                rows=[{
                    "total_schemas": total_schemas,
                    "bronze_count": bronze_count,
                    "silver_count": silver_count,
                    "gold_count": gold_count,
                }],
                ref=(
                    "https://docs.databricks.com/en/lakehouse/medallion-architecture.html"
                ),
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total_schemas = row["total_schemas"]
        bronze_count = row["bronze_count"]
        silver_count = row["silver_count"]
        gold_count = row["gold_count"]

        if total_schemas == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No schemas found in information_schema.schemata to evaluate "
                    "medallion layer naming."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        families_present = sum(
            1 for c in (bronze_count, silver_count, gold_count) if c > 0
        )
        score = round(families_present / 3, 4)

        if families_present == 3:
            verdict = Verdict.MET
        elif families_present >= 1:
            verdict = Verdict.PARTIAL
        else:
            verdict = Verdict.NOT_MET

        detected = []
        if bronze_count > 0:
            detected.append(f"bronze ({bronze_count})")
        if silver_count > 0:
            detected.append(f"silver ({silver_count})")
        if gold_count > 0:
            detected.append(f"gold ({gold_count})")
        missing = [
            name
            for name, count in (
                ("bronze", bronze_count),
                ("silver", silver_count),
                ("gold", gold_count),
            )
            if count == 0
        ]

        rationale_parts = [
            f"{families_present} of 3 medallion layer families detected by schema name "
            f"across {total_schemas} schema(s)."
        ]
        if detected:
            rationale_parts.append(f"Present: {', '.join(detected)}.")
        if missing:
            rationale_parts.append(f"Not detected: {', '.join(missing)}.")
        rationale_parts.append(
            "Detection is based on schema naming conventions (bronze|raw|_brz|landing, "
            "silver|refined|clean|_slv|staging, gold|curated|serving|mart|_gld); "
            "confirm with a reviewer."
        )

        return Finding(
            question_id=question.id,
            pillar_id=question.pillar_id,
            verdict=verdict,
            confidence=Confidence.MEDIUM,
            score=score,
            rationale=" ".join(rationale_parts),
            sources=evidence,
        )
