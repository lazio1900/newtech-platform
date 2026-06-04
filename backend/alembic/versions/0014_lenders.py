"""lenders: 대부업체(차주) 마스터

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lenders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_name", sa.String(length=200), nullable=False),
        sa.Column("business_number", sa.String(length=20), nullable=True),
        sa.Column("ceo_name", sa.String(length=80), nullable=True),
        sa.Column("credit_score_nice", sa.Integer(), nullable=True),
        sa.Column("credit_score_kcb", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("business_number", name="uq_lenders_business_number"),
    )
    op.create_index("ix_lenders_id", "lenders", ["id"])
    op.create_index("ix_lenders_company_name", "lenders", ["company_name"])


def downgrade() -> None:
    op.drop_index("ix_lenders_company_name", table_name="lenders")
    op.drop_index("ix_lenders_id", table_name="lenders")
    op.drop_table("lenders")
