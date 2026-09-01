"""Feature store adoption check (deterministic).

Answers:
  ML-IU-02  Share reusable features via a feature store

Signal: the share of UC managed/external tables in schemas whose names suggest a
feature-store pattern (names containing 'feature', 'feat_', 'feature_store', 'fs_')
versus all UC managed/external tables. A non-zero ratio indicates some feature-store
patterns are present in Unity Catalog.

Deterministic ratio vs a threshold -> Medium confidence (schema-name matching is a proxy).

Limitation: the Databricks Feature Store API registers feature tables as regular UC
MANAGED tables; their schema names are chosen by the team and may not contain 'feature'.
A workspace with a rigorous feature store backed by schemas named differently will appear
as NOT_MET. Manual confirmation of actual feature store schema paths is recommended.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.05    # ≥5 % of UC tables are in feature-store-like schemas
_PARTIAL_THRESHOLD = 0.005  # at least a handful in a typical estate

# Feature-store-suggestive tables in Unity Catalog.
_FEATURE_TABLES_SQL = (
    "SELECT COUNT(*) AS feature_tables "
    "FROM system.information_schema.tables "
    "WHERE table_type IN ('MANAGED','EXTERNAL') "
    "  AND table_catalog <> 'hive_metastore' "
    "  AND (LOWER(table_schema) LIKE '%feature%' "
    "       OR LOWER(table_schema) LIKE '%feat_%' "
    "       OR LOWER(table_schema) LIKE '%fs_%' "
    "       OR LOWER(table_name) LIKE '%_features')"
)

# Total UC managed/external tables for denominator.
_TOTAL_UC_SQL = (
    "SELECT COUNT(*) AS total_uc_tables "
    "FROM system.information_schema.tables "
    "WHERE table_type IN ('MANAGED','EXTERNAL') "
    "  AND table_catalog <> 'hive_metastore'"
)

_REF = (
    "https://docs.databricks.com/en/machine-learning/feature-store/uc/feature-tables-uc.html"
)


@register(layer="ml", question_ids=["ML-IU-02"])
class MlFeatureStoreCheck(Check):
    """Deterministic check for ML-IU-02: feature store adoption in Unity Catalog."""

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        feature_rows = ctx.sql.query(_FEATURE_TABLES_SQL)
        total_rows = ctx.sql.query(_TOTAL_UC_SQL)

        feature_tables = int(
            (feature_rows[0].get("feature_tables") or 0) if feature_rows else 0
        )
        total_uc = int((total_rows[0].get("total_uc_tables") or 0) if total_rows else 0)

        return [
            Evidence(
                kind="sql",
                summary=(
                    f"{feature_tables} tables in feature-store-suggestive schemas "
                    f"out of {total_uc} total UC managed/external tables"
                ),
                detail=f"{_FEATURE_TABLES_SQL}\n{_TOTAL_UC_SQL}",
                rows=[{"feature_tables": feature_tables, "total_uc_tables": total_uc}],
                ref=_REF,
            )
        ]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        feature_tables = row["feature_tables"]
        total_uc = row["total_uc_tables"]

        if total_uc == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No UC managed/external tables found; cannot evaluate feature store adoption."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        ratio = feature_tables / total_uc
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
            confidence=Confidence.MEDIUM,
            score=round(ratio, 4),
            rationale=(
                f"{feature_tables} of {total_uc} UC tables ({ratio:.1%}) are in "
                "feature-store-suggestive schemas (names containing 'feature', 'feat_', "
                f"'fs_', or ending '_features'); threshold for 'met' is {_MET_THRESHOLD:.0%}. "
                "Schema-name matching is a proxy — manual confirmation of actual feature store "
                "schema paths is recommended."
            ),
            sources=evidence,
        )
