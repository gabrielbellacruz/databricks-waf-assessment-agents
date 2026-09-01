"""create backlog_runs table

Revision ID: 0004_create_backlog_runs
Revises: 0003_add_notes_to_assessments
Create Date: 2026-08-31

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0004_create_backlog_runs"
down_revision = "0003_add_notes_to_assessments"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "backlog_runs",
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("assessment_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column(
            "tasks",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
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
    op.create_index(
        "ix_backlog_runs_assessment_id", "backlog_runs", ["assessment_id"]
    )


def downgrade():
    op.drop_index("ix_backlog_runs_assessment_id", table_name="backlog_runs")
    op.drop_table("backlog_runs")
