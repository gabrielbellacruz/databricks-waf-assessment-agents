"""add notes column to assessments

Revision ID: 0003_add_notes_to_assessments
Revises: 0002_create_agent_tables
Create Date: 2026-08-26

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0003_add_notes_to_assessments"
down_revision = "0002_create_agent_tables"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "assessments",
        sa.Column(
            "notes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade():
    op.drop_column("assessments", "notes")
