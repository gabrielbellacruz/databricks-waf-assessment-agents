"""Sensitive training data protection check (LLM-judged).

Answers:
  ML-SCP-02  Protect sensitive training data

Signals:
1. Row-level security and column masking on Unity Catalog tables: presence of
   row filters and column masks in ``system.information_schema`` indicates that
   data governance controls are applied on the tables ML models read from.

2. Audit events for data access by service principals: how many distinct
   principals have accessed data (selectFromTable actions) in system tables
   over the last 30 days — a proxy for whether access is controlled and
   attributed.

Limitation: it is not possible to determine which tables a specific model was
trained on from system tables alone. Row filters and column masks protect
tables broadly, but whether they apply to the specific features / raw data used
for ML training requires manual confirmation. Training data in external storage
(S3, ADLS) with no UC external table is not observable.
"""

from __future__ import annotations

from waf_agents.core.clients import AgentContext
from waf_agents.core.llm import judge_with_llm
from waf_agents.core.models import Evidence, Finding, Question
from waf_agents.core.registry import Check, register

_ROW_FILTERS_SQL = """\
SELECT COUNT(*) AS tables_with_row_filter,
       COUNT(DISTINCT table_catalog) AS catalogs_covered
FROM system.information_schema.row_filters
WHERE table_catalog <> 'hive_metastore'\
"""

_COL_MASKS_SQL = """\
SELECT COUNT(*) AS columns_with_mask,
       COUNT(DISTINCT table_catalog) AS catalogs_covered
FROM system.information_schema.column_masks
WHERE table_catalog <> 'hive_metastore'\
"""

_DATA_ACCESS_SQL = """\
SELECT COUNT(DISTINCT user_identity.email) AS distinct_readers,
       SUM(CASE WHEN user_identity.email NOT LIKE '%@%'
                THEN 1 ELSE 0 END) AS sp_reads
FROM system.access.audit
WHERE event_date >= current_date() - INTERVAL 30 DAYS
  AND action_name IN ('selectFromTable', 'readResource', 'getTable')
  AND service_name IN ('unityCatalog', 'dataAccess', 'databricks')\
"""

_NOTE = (
    "Row filters and column masks in Unity Catalog protect tables at the catalog layer, "
    "but the system tables do not identify which specific tables were used as ML training "
    "data. Training data in external storage without a UC external table is not observable. "
    "Whether data minimization (using only necessary features), anonymization, or differential "
    "privacy is applied requires manual review of the training pipeline code and feature "
    "store setup."
)

_REF = "https://docs.databricks.com/en/data-governance/unity-catalog/row-and-column-filters.html"


@register(layer="ml", question_ids=["ML-SCP-02"])
class SensitiveTrainingDataCheck(Check):
    """Assess training data protection via UC row filters, column masks, and access audit.

    Evidence:
    - system.information_schema: tables with row filters and columns with masks.
    - system.access.audit: distinct readers and SP share for data access events.
    A note records that training-specific data lineage is not observable from
    system tables.
    """

    def collect(self, ctx: AgentContext) -> list[Evidence]:
        filter_rows = ctx.sql.query(_ROW_FILTERS_SQL)
        mask_rows = ctx.sql.query(_COL_MASKS_SQL)
        access_rows = ctx.sql.query(_DATA_ACCESS_SQL)

        f = filter_rows[0] if filter_rows else {}
        tables_with_filter = int(f.get("tables_with_row_filter") or 0)
        filter_catalogs = int(f.get("catalogs_covered") or 0)

        filter_evidence = Evidence(
            kind="sql",
            summary=(
                f"{tables_with_filter} table(s) with a UC row filter "
                f"across {filter_catalogs} catalog(s)"
            ),
            detail=_ROW_FILTERS_SQL,
            rows=[{
                "tables_with_row_filter": tables_with_filter,
                "catalogs_covered": filter_catalogs,
            }],
            ref=_REF,
        )

        m = mask_rows[0] if mask_rows else {}
        columns_with_mask = int(m.get("columns_with_mask") or 0)
        mask_catalogs = int(m.get("catalogs_covered") or 0)

        mask_evidence = Evidence(
            kind="sql",
            summary=(
                f"{columns_with_mask} column(s) with a UC column mask "
                f"across {mask_catalogs} catalog(s)"
            ),
            detail=_COL_MASKS_SQL,
            rows=[{"columns_with_mask": columns_with_mask, "catalogs_covered": mask_catalogs}],
            ref=_REF,
        )

        a = access_rows[0] if access_rows else {}
        distinct_readers = int(a.get("distinct_readers") or 0)
        sp_reads = int(a.get("sp_reads") or 0)

        access_evidence = Evidence(
            kind="sql",
            summary=(
                f"{distinct_readers} distinct principal(s) accessed data tables in "
                f"the last 30 days; {sp_reads} event(s) from service-principal identities "
                "(system.access.audit)"
            ),
            detail=_DATA_ACCESS_SQL,
            rows=[{"distinct_readers": distinct_readers, "sp_reads": sp_reads}],
            ref="https://docs.databricks.com/en/admin/system-tables/audit.html",
        )

        note_evidence = Evidence(
            kind="note",
            summary=_NOTE,
            rows=[],
            ref=_REF,
        )

        return [filter_evidence, mask_evidence, access_evidence, note_evidence]

    def judge(self, evidence: list[Evidence], question: Question, ctx: AgentContext) -> Finding:
        return judge_with_llm(ctx, question, evidence)
