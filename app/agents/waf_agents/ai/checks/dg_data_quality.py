"""Data quality for AI grounding check (LLM-judged).

Answers:
  AI-DG-04  Ensure quality of data grounding generative apps

Signal:
  1. system.information_schema.table_constraints — declared NOT NULL / CHECK /
     PRIMARY KEY constraints indicate data-integrity rules on tables that may
     ground generative AI apps (RAG, structured Q&A, etc.).
  2. system.information_schema.column_tags — classification/quality tags applied
     to columns; high tag coverage is a proxy for data governance maturity.

Limitation note: The SP cannot identify which specific tables feed RAG pipelines
or LLM grounding contexts. These signals apply workspace-wide and are a proxy for
general data-quality culture rather than AI-specific quality gates. AI-specific
DLT expectations or monitoring jobs must be assessed via the Databricks UI or
Pipeline REST API.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_CONSTRAINTS_SQL = (
    "SELECT COUNT(*) AS ai_dq_constraints,"
    " COUNT(DISTINCT table_catalog||'.'||table_schema||'.'||table_name)"
    "  AS constrained_tables"
    " FROM system.information_schema.table_constraints"
    " WHERE table_catalog <> 'hive_metastore'"
    " AND constraint_type IN ('NOT_NULL','CHECK','PRIMARY KEY','FOREIGN KEY')"
)

_TAGS_SQL = (
    "SELECT COUNT(*) AS ai_dq_column_tags,"
    " COUNT(DISTINCT catalog_name||'.'||schema_name||'.'||table_name)"
    "  AS tagged_tables"
    " FROM system.information_schema.column_tags"
)

_REF = (
    "https://docs.databricks.com/en/lakehouse-monitoring/index.html"
)

_GROUNDING_LIMITATION = (
    "Tables that ground generative AI apps (RAG indices, vector stores, structured"
    " knowledge bases) cannot be identified from system.information_schema alone."
    " Constraint and tag signals are workspace-wide proxies for data-quality maturity."
    " AI-specific DLT expectations or Lakehouse Monitoring alerts require separate review."
)


@register(layer="ai", question_ids=["AI-DG-04"])
class AiDataQualityCheck(Check):
    def collect(self, ctx: AgentContext) -> list[Evidence]:
        constraint_rows = ctx.sql.query(_CONSTRAINTS_SQL)
        tag_rows = ctx.sql.query(_TAGS_SQL)

        c = constraint_rows[0] if constraint_rows else {}
        constraint_count = int(c.get("ai_dq_constraints") or 0)
        constrained_tables = int(c.get("constrained_tables") or 0)

        t = tag_rows[0] if tag_rows else {}
        tag_count = int(t.get("ai_dq_column_tags") or 0)
        tagged_tables = int(t.get("tagged_tables") or 0)

        constraint_evidence = Evidence(
            kind="sql",
            summary=(
                f"{constraint_count} table constraint(s) across {constrained_tables}"
                " UC table(s) (NOT NULL, CHECK, PK/FK)"
            ),
            detail=_CONSTRAINTS_SQL,
            rows=[{
                "ai_dq_constraints": constraint_count,
                "constrained_tables": constrained_tables,
            }],
            ref=_REF,
        )
        tag_evidence = Evidence(
            kind="sql",
            summary=(
                f"{tag_count} column tag(s) across {tagged_tables} table(s) in"
                " system.information_schema.column_tags"
            ),
            detail=_TAGS_SQL,
            rows=[{"ai_dq_column_tags": tag_count, "tagged_tables": tagged_tables}],
            ref=_REF,
        )
        limitation = Evidence(
            kind="uc_metadata",
            summary=_GROUNDING_LIMITATION,
            detail=(
                "Use Lakehouse Monitoring or DLT expectations to add AI-specific"
                " quality gates. Identify grounding tables by reviewing app code"
                " or Vector Search index configurations."
            ),
            ref=_REF,
        )
        return [constraint_evidence, tag_evidence, limitation]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
