"""create agent_runs and agent_findings tables

Revision ID: 0002_create_agent_tables
Revises: 0001_create_assessments
Create Date: 2026-08-19

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0002_create_agent_tables"
down_revision = "0001_create_assessments"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_runs",
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("assessment_id", sa.Text(), nullable=False),
        sa.Column("layer", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("n_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("job_run_id", sa.Text(), nullable=True),
        sa.Column("agent_version", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["assessment_id"], ["assessments.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index("ix_agent_runs_assessment_id", "agent_runs", ["assessment_id"])

    op.create_table(
        "agent_findings",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("assessment_id", sa.Text(), nullable=False),
        sa.Column("category_id", sa.Text(), nullable=False),
        sa.Column("pillar_id", sa.Text(), nullable=False),
        sa.Column("question_id", sa.Text(), nullable=False),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "sources",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "auto_assessable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["agent_runs.run_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "question_id", name="uq_finding_run_question"),
    )
    op.create_index(
        "ix_agent_findings_run_id", "agent_findings", ["run_id"]
    )
    op.create_index(
        "ix_agent_findings_assessment_id", "agent_findings", ["assessment_id"]
    )


def downgrade():
    op.drop_index("ix_agent_findings_assessment_id", table_name="agent_findings")
    op.drop_index("ix_agent_findings_run_id", table_name="agent_findings")
    op.drop_table("agent_findings")
    op.drop_index("ix_agent_runs_assessment_id", table_name="agent_runs")
    op.drop_table("agent_runs")
