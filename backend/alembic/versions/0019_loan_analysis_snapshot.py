"""add analysis_snapshot (분석 전체 박제) to loan_applications

Revision ID: 0019
Revises: 0018
Create Date: 2026-06-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "loan_applications",
        sa.Column("analysis_snapshot", sa.Text(), nullable=True),
    )
    op.add_column(
        "loan_applications",
        sa.Column("analysis_snapshot_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("loan_applications", "analysis_snapshot_at")
    op.drop_column("loan_applications", "analysis_snapshot")
