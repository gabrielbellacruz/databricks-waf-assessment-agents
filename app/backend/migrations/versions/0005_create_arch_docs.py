"""create architecture_documents table

Revision ID: 0005_create_arch_docs
Revises: 0004_create_backlog_runs
Create Date: 2026-09-01

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0005_create_arch_docs"
down_revision = "0004_create_backlog_runs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "architecture_documents",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("assessment_id", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("volume_path", sa.Text(), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"], ["assessments.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_architecture_documents_assessment_id",
        "architecture_documents",
        ["assessment_id"],
    )


def downgrade():
    op.drop_index(
        "ix_architecture_documents_assessment_id",
        table_name="architecture_documents",
    )
    op.drop_table("architecture_documents")
