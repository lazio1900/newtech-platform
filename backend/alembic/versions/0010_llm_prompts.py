"""create llm_prompts table for admin-editable system prompts

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_prompts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("feature_key", sa.String(length=60), nullable=False),
        sa.Column("prompt_key", sa.String(length=40), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_by", sa.String(length=80), nullable=True),
        sa.UniqueConstraint("feature_key", "prompt_key", name="uq_llm_prompts_feature_key"),
    )
    op.create_index("ix_llm_prompts_feature_key", "llm_prompts", ["feature_key"])


def downgrade() -> None:
    op.drop_index("ix_llm_prompts_feature_key", table_name="llm_prompts")
    op.drop_table("llm_prompts")
