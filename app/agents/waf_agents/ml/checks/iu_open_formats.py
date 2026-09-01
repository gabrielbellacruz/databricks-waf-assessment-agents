"""Open ML formats and formats check (deterministic).

Answers:
  ML-IU-01  Use open ML frameworks and formats

Signal: the share of UC managed/external tables using an open table/file format
(Delta, Parquet, ORC, Avro) versus all UC managed/external tables. Delta is the
dominant open format on Databricks; a high share indicates that data artifacts are
stored in interoperable, open formats.

Deterministic ratio vs a threshold -> High confidence.

Limitation: ML framework selection (TensorFlow, PyTorch, Scikit-learn, XGBoost, etc.)
is not observable from system.information_schema — no system table records which
libraries are used to train or serve models. This check measures open data-format
adoption as an infrastructure-level proxy for open-standards compliance.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.models import Confidence, Evidence, Finding, Question, Verdict
from waf_agents.core.registry import Check, register

_MET_THRESHOLD = 0.80
_PARTIAL_THRESHOLD = 0.50

_FORMAT_SQL = (
    "SELECT COUNT(*) AS total_uc_tables, "
    "SUM(CASE WHEN data_source_format IN ('DELTA','PARQUET','ORC','AVRO') "
    "    THEN 1 ELSE 0 END) AS open_format_tables "
    "FROM system.information_schema.tables "
    "WHERE table_type IN ('MANAGED','EXTERNAL') "
    "  AND table_catalog <> 'hive_metastore'"
)

_NOTE = (
    "ML framework choice (TensorFlow, PyTorch, Scikit-learn, XGBoost, etc.) is not "
    "recorded in system.information_schema. Open data-format adoption (Delta/Parquet/ORC/Avro) "
    "is used as a measurable proxy for open-standards compliance at the storage layer. "
    "Manual confirmation of framework and serialisation-format choices is recommended."
)

_REF = "https://docs.databricks.com/en/machine-learning/index.html"


@register(layer="ml", question_ids=["ML-IU-01"])
class MlOpenFormatsCheck(Check):
    """Deterministic check for ML-IU-01: open formats adoption in Unity Catalog."""

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        rows = ctx.sql.query(_FORMAT_SQL)
        row = rows[0] if rows else {"total_uc_tables": 0, "open_format_tables": 0}
        total = int(row.get("total_uc_tables") or 0)
        open_fmt = int(row.get("open_format_tables") or 0)

        sql_evidence = Evidence(
            kind="sql",
            summary=(
                f"{open_fmt} of {total} UC managed/external tables use an open format "
                "(Delta, Parquet, ORC, or Avro)"
            ),
            detail=_FORMAT_SQL,
            rows=[{"total_uc_tables": total, "open_format_tables": open_fmt}],
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
        total = row["total_uc_tables"]
        open_fmt = row["open_format_tables"]

        if total == 0:
            return Finding(
                question_id=question.id,
                pillar_id=question.pillar_id,
                verdict=Verdict.UNKNOWN,
                confidence=Confidence.LOW,
                rationale=(
                    "No managed or external UC tables found; cannot evaluate open-format adoption."
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
                f"{open_fmt} of {total} UC managed/external tables ({ratio:.0%}) use "
                "Delta, Parquet, ORC, or Avro; "
                f"threshold for 'met' is {_MET_THRESHOLD:.0%}. "
                "ML framework observability is limited — see note evidence."
            ),
            sources=evidence,
        )
