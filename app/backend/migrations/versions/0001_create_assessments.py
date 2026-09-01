"""create assessments table

Revision ID: 0001_create_assessments
Revises:
Create Date: 2026-08-07

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_create_assessments"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "assessments",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "description", sa.Text(), nullable=False, server_default=""
        ),
        sa.Column(
            "categories",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("cloud_provider", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("imported_at", sa.Text(), nullable=True),
        sa.Column(
            "answers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("assessments")
