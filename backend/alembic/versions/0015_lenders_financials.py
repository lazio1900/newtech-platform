"""lenders: direct_debt + guarantee_debt + financial_data

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("lenders", sa.Column("direct_debt", sa.BigInteger(), nullable=True))
    op.add_column("lenders", sa.Column("guarantee_debt", sa.BigInteger(), nullable=True))
    op.add_column("lenders", sa.Column("financial_data", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("lenders", "financial_data")
    op.drop_column("lenders", "guarantee_debt")
    op.drop_column("lenders", "direct_debt")
