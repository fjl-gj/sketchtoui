"""Add account state and versioned project imports.

Revision ID: 0002_core_project_versions
Revises: 0001_initial_schema
Create Date: 2026-07-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_core_project_versions"
down_revision: Union[str, Sequence[str], None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("phone", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.text("1")))
        batch.add_column(sa.Column("email_verified_at", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("status", sa.String(length=32), nullable=False, server_default="active"))
        batch.add_column(sa.Column("last_login_at", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("updated_at", sa.String(length=40), nullable=True))
        batch.create_unique_constraint("uq_users_phone", ["phone"])
        batch.create_index("idx_users_email_verified", ["email_verified"])
        batch.create_index("idx_users_status", ["status"])
    op.execute("UPDATE users SET email_verified_at = created_at, updated_at = created_at WHERE updated_at IS NULL")
    with op.batch_alter_table("users") as batch:
        batch.alter_column("updated_at", existing_type=sa.String(length=40), nullable=False)

    with op.batch_alter_table("projects") as batch:
        batch.alter_column("source_filename", new_column_name="filename", existing_type=sa.String(length=512))
        batch.add_column(sa.Column("current_version_id", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("status", sa.String(length=32), nullable=False, server_default="ready"))
        batch.add_column(sa.Column("updated_at", sa.String(length=40), nullable=True))
        batch.create_index("idx_projects_user_status", ["user_id", "status"])
    op.execute("UPDATE projects SET updated_at = created_at WHERE updated_at IS NULL")
    with op.batch_alter_table("projects") as batch:
        batch.alter_column("updated_at", existing_type=sa.String(length=40), nullable=False)

    op.create_table(
        "project_versions",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_bytes", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("extracted_bytes", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("canvas_bytes", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("preview_bytes", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_bytes", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("object_prefix", sa.String(length=512), nullable=False, unique=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("manifest_path", sa.String(length=1024), nullable=True),
        sa.Column("group_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("artboard_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("layer_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("completed_at", sa.String(length=40), nullable=True),
        sa.UniqueConstraint("project_id", "version_number", name="uq_project_versions_number"),
    )
    op.create_index("idx_project_versions_project_number", "project_versions", ["project_id", "version_number"])
    op.create_index("idx_project_versions_status", "project_versions", ["status"])
    op.create_index("idx_project_versions_total_bytes", "project_versions", ["total_bytes"])

    op.create_table(
        "import_jobs",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("project_version_id", sa.String(length=32), nullable=False, unique=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("stage", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("progress", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("message", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("attempt", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("started_at", sa.String(length=40), nullable=True),
        sa.Column("finished_at", sa.String(length=40), nullable=True),
    )
    op.create_index("idx_import_jobs_user_created", "import_jobs", ["user_id", "created_at"])
    op.create_index("idx_import_jobs_project", "import_jobs", ["project_id"])
    op.create_index("idx_import_jobs_status", "import_jobs", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_import_jobs_status", table_name="import_jobs")
    op.drop_index("idx_import_jobs_project", table_name="import_jobs")
    op.drop_index("idx_import_jobs_user_created", table_name="import_jobs")
    op.drop_table("import_jobs")

    op.drop_index("idx_project_versions_total_bytes", table_name="project_versions")
    op.drop_index("idx_project_versions_status", table_name="project_versions")
    op.drop_index("idx_project_versions_project_number", table_name="project_versions")
    op.drop_table("project_versions")

    with op.batch_alter_table("projects") as batch:
        batch.drop_index("idx_projects_user_status")
        batch.drop_column("updated_at")
        batch.drop_column("status")
        batch.drop_column("current_version_id")
        batch.alter_column("filename", new_column_name="source_filename", existing_type=sa.String(length=512))

    with op.batch_alter_table("users") as batch:
        batch.drop_index("idx_users_status")
        batch.drop_index("idx_users_email_verified")
        batch.drop_constraint("uq_users_phone", type_="unique")
        batch.drop_column("updated_at")
        batch.drop_column("last_login_at")
        batch.drop_column("status")
        batch.drop_column("email_verified_at")
        batch.drop_column("email_verified")
        batch.drop_column("phone")
