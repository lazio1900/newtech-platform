"""llm_prompts: version + is_active + (feature_key, prompt_key) 당 활성 1개 보장

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "llm_prompts",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "llm_prompts",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "llm_prompts",
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # 기존 UNIQUE 제약 교체: (feature_key, prompt_key) → (feature_key, prompt_key, version)
    op.drop_constraint("uq_llm_prompts_feature_key", "llm_prompts", type_="unique")
    op.create_unique_constraint(
        "uq_llm_prompts_fk_pk_ver",
        "llm_prompts",
        ["feature_key", "prompt_key", "version"],
    )

    # 활성 row 는 (feature_key, prompt_key) 당 1개만 — partial unique index (PostgreSQL)
    op.create_index(
        "uq_llm_prompts_active",
        "llm_prompts",
        ["feature_key", "prompt_key"],
        unique=True,
        postgresql_where=sa.text("is_active = TRUE"),
    )


def downgrade() -> None:
    op.drop_index("uq_llm_prompts_active", table_name="llm_prompts")
    op.drop_constraint("uq_llm_prompts_fk_pk_ver", "llm_prompts", type_="unique")
    op.create_unique_constraint(
        "uq_llm_prompts_feature_key",
        "llm_prompts",
        ["feature_key", "prompt_key"],
    )
    op.drop_column("llm_prompts", "created_at")
    op.drop_column("llm_prompts", "is_active")
    op.drop_column("llm_prompts", "version")
