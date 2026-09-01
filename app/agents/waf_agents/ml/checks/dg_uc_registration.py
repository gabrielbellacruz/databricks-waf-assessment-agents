"""Unity Catalog registration check for ML objects (deterministic).

Answers:
  ML-DG-01  Register models and features in Unity Catalog

Signal: UC-registered ML objects — models (table_type = 'MODEL') plus tables in
ML-suggestive schemas (feature*, model*, ml*, train*) outside hive_metastore —
versus the same schema patterns in hive_metastore.

Deterministic ratio with MEDIUM confidence because schema-name matching is a proxy.

Limitations:
  * MLflow Model Registry objects appear in information_schema as table_type = 'MODEL'
    only when Unity Catalog mode is enabled; the legacy Workspace Model Registry is not
    reflected here, so a workspace still on the legacy registry will appear as NOT_MET
    even if it has many registered models.
  * Feature tables are regular UC MANAGED tables; their presence is inferred by schema
    naming rather than a first-class Feature Store tag.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.80
_PARTIAL_THRESHOLD = 0.40

# UC-registered ML objects: UC models (any catalog) + tables in ML-suggestive schemas.
_UC_ML_SQL = (
    "SELECT COUNT(*) AS uc_ml_count "
    "FROM system.information_schema.tables "
    "WHERE table_catalog <> 'hive_metastore' "
    "  AND (table_type = 'MODEL' "
    "       OR (table_type IN ('MANAGED','EXTERNAL') "
    "           AND (LOWER(table_schema) LIKE '%feature%' "
    "                OR LOWER(table_schema) LIKE '%model%' "
    "                OR LOWER(table_schema) LIKE '%ml%' "
    "                OR LOWER(table_schema) LIKE '%train%')))"
)

# Legacy ML objects: same schema patterns in hive_metastore.
_LEGACY_ML_SQL = (
    "SELECT COUNT(*) AS legacy_ml_count "
    "FROM system.information_schema.tables "
    "WHERE table_catalog = 'hive_metastore' "
    "  AND table_type IN ('MANAGED','EXTERNAL') "
    "  AND (LOWER(table_schema) LIKE '%feature%' "
    "       OR LOWER(table_schema) LIKE '%model%' "
    "       OR LOWER(table_schema) LIKE '%ml%' "
    "       OR LOWER(table_schema) LIKE '%train%')"
)

_NOTE = (
    "UC model registry objects appear in information_schema only when the workspace uses "
    "Unity Catalog model registry; legacy Workspace Model Registry models are not visible "
    "here. Feature tables are inferred by schema naming (feature*, model*, ml*, train*). "
    "This check is a proxy — manual confirmation of the feature store and model registry "
    "topology is recommended."
)

_REF = "https://docs.databricks.com/en/machine-learning/manage-model-lifecycle/index.html"


@register(layer="ml", question_ids=["ML-DG-01"])
class MlUcRegistrationCheck(Check):
    """Deterministic check for ML-DG-01: models and features registered in Unity Catalog."""

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        uc_rows = ctx.sql.query(_UC_ML_SQL)
        legacy_rows = ctx.sql.query(_LEGACY_ML_SQL)

        uc_ml = int((uc_rows[0].get("uc_ml_count") or 0) if uc_rows else 0)
        legacy_ml = int((legacy_rows[0].get("legacy_ml_count") or 0) if legacy_rows else 0)

        sql_evidence = Evidence(
            kind="sql",
            summary=(
                f"{uc_ml} ML-suggestive objects (models or feature/model/ml/train-named "
                f"schema tables) in Unity Catalog; {legacy_ml} equivalent objects remain "
                "in hive_metastore"
            ),
            detail=f"{_UC_ML_SQL}\n{_LEGACY_ML_SQL}",
            rows=[{"uc_ml_count": uc_ml, "legacy_ml_count": legacy_ml}],
            ref=_REF,
        )
        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )
        return [sql_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        row = evidence[0].rows[0]
        uc_ml = row["uc_ml_count"]
        legacy_ml = row["legacy_ml_count"]
        total = uc_ml + legacy_ml

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No ML-suggestive tables or models found in information_schema. "
                    "Either no ML workloads exist yet, or models are stored in the legacy "
                    "Workspace Model Registry (not visible here). Manual review required."
                ),
                sources=evidence,
                auto_assessable=True,
            )

        ratio = uc_ml / total
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
                f"{uc_ml} of {total} ML-suggestive objects ({ratio:.0%}) are registered in "
                f"Unity Catalog; {legacy_ml} remain in hive_metastore. "
                f"Threshold for 'met' is {_MET_THRESHOLD:.0%}. "
                "Schema-name matching is a proxy — legacy Workspace Model Registry models "
                "are not visible in information_schema."
            ),
            sources=evidence,
        )
