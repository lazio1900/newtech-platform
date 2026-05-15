"""create data_source_mappings table for external → internal schema adapters

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "data_source_mappings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("logical_entity", sa.String(length=40), nullable=False),
        sa.Column("source_db_connection_id", sa.Integer(), sa.ForeignKey("db_connections.id"), nullable=False),
        sa.Column("source_table", sa.String(length=200), nullable=False),
        sa.Column("field_mappings", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_by", sa.String(length=80), nullable=True),
        sa.UniqueConstraint("source_db_connection_id", "logical_entity",
                            name="uq_data_source_mappings_db_entity"),
    )
    op.create_index("ix_data_source_mappings_entity", "data_source_mappings", ["logical_entity"])


def downgrade() -> None:
    op.drop_index("ix_data_source_mappings_entity", table_name="data_source_mappings")
    op.drop_table("data_source_mappings")
