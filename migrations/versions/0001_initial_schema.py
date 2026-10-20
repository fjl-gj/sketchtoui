"""Create the SketchToUI application schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False, unique=True),
        sa.Column("username", sa.String(length=64), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
    )
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_filename", sa.String(length=512), nullable=False),
        sa.Column("group_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
    )
    op.create_index("idx_projects_user", "projects", ["user_id"])
    op.create_table(
        "mcp_tokens",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("token_prefix", sa.String(length=24), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("scopes_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("last_used_at", sa.String(length=40), nullable=True),
        sa.Column("expires_at", sa.String(length=40), nullable=True),
        sa.Column("revoked_at", sa.String(length=40), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )
    op.create_index("idx_mcp_tokens_user", "mcp_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_mcp_tokens_user", table_name="mcp_tokens")
    op.drop_table("mcp_tokens")
    op.drop_index("idx_projects_user", table_name="projects")
    op.drop_table("projects")
    op.drop_table("users")
