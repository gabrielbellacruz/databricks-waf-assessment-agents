"""DBFS root avoidance check (deterministic).

Answers:
  STO-SCP-03  Avoid storing production data in DBFS root

Signal: of tables with a known storage path, the share sitting on the DBFS
root (``dbfs:/`` but NOT ``dbfs:/mnt/``) from
``system.information_schema.tables``.  Tables in hive_metastore are counted
separately as a secondary evidence signal for legacy/DBFS-associated data.
Deterministic ratio vs a threshold -> High confidence.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

# Fraction of *located* tables ON the DBFS root that triggers each verdict.
# MET means almost no data lives on DBFS root; NOT_MET means a substantial
# share does.
_MET_THRESHOLD = 0.05     # <= 5 % on DBFS root -> MET
_PARTIAL_THRESHOLD = 0.20  # <= 20 % -> PARTIAL; > 20 % -> NOT_MET


@register(layer="storage", question_ids=["STO-SCP-03"])
class DbfsRootAvoidanceCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        # Primary signal: tables whose storage path is known and whether they
        # point at DBFS root (dbfs:/ but not dbfs:/mnt/).
        sql_main = (
            "SELECT "
            "COUNT(*) AS total_located, "
            "SUM(CASE WHEN lower(storage_path) LIKE 'dbfs:/%' "
            "AND lower(storage_path) NOT LIKE 'dbfs:/mnt/%' "
            "THEN 1 ELSE 0 END) AS on_dbfs_root "
            "FROM system.information_schema.tables "
            "WHERE table_type IN ('MANAGED', 'EXTERNAL') "
            "AND storage_path IS NOT NULL"
        )
        rows_main = ctx.sql.query(sql_main)
        row_main = rows_main[0] if rows_main else {"total_located": 0, "on_dbfs_root": 0}
        total_located = int(row_main.get("total_located") or 0)
        on_dbfs_root = int(row_main.get("on_dbfs_root") or 0)

        # Secondary signal: hive_metastore tables are a strong proxy for
        # legacy / DBFS-associated data even when storage_path is NULL.
        sql_hive = (
            "SELECT COUNT(*) AS hive_tables "
            "FROM system.information_schema.tables "
            "WHERE table_catalog = 'hive_metastore' "
            "AND table_type IN ('MANAGED', 'EXTERNAL')"
        )
        rows_hive = ctx.sql.query(sql_hive)
        hive_tables = int(
            (rows_hive[0].get("hive_tables") if rows_hive else None) or 0
        )

        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{on_dbfs_root} of {total_located} tables with a known storage path "
                    f"sit on the DBFS root (dbfs:/ but not dbfs:/mnt/)"
                ),
                detail=sql_main,
                rows=[{"total_located": total_located, "on_dbfs_root": on_dbfs_root}],
                ref="https://docs.databricks.com/en/dbfs/dbfs-root.html",
            ),
            Evidence(
                kind="sql",
                summary=(
                    f"{hive_tables} table(s) remain in hive_metastore "
                    f"(legacy / DBFS-associated)"
                ),
                detail=sql_hive,
                rows=[{"hive_tables": hive_tables}],
                ref="https://docs.databricks.com/en/data-governance/unity-catalog/index.html",
            ),
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        total_located = row["total_located"]
        on_dbfs_root = row["on_dbfs_root"]
        hive_tables = evidence[1].rows[0]["hive_tables"]

        if total_located == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No tables with a known storage path found; cannot assess "
                    "DBFS root usage."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        fraction = on_dbfs_root / total_located
        score = round(1.0 - fraction, 4)

        if fraction <= _MET_THRESHOLD:
            verdict = Verdict.MET
        elif fraction <= _PARTIAL_THRESHOLD:
            verdict = Verdict.PARTIAL
        else:
            verdict = Verdict.NOT_MET

        hive_note = (
            f" Additionally, {hive_tables} table(s) reside in hive_metastore "
            f"(legacy / DBFS-associated)."
            if hive_tables
            else ""
        )

        return Finding(
            question_id=question.id,
            pillar_id=question.pillar_id,
            verdict=verdict,
            confidence=Confidence.HIGH,
            score=score,
            rationale=(
                f"Of {total_located} tables with a known storage path, {on_dbfs_root} "
                f"({fraction:.0%}) sit on the DBFS root (dbfs:/ excluding dbfs:/mnt/); "
                f"threshold for 'met' is ≤{_MET_THRESHOLD:.0%} on DBFS root.{hive_note}"
            ),
            sources=evidence,
        )
