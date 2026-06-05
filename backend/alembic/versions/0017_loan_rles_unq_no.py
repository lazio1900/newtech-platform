"""add rles_unq_no (부동산고유번호) to loan_applications

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "loan_applications",
        sa.Column("rles_unq_no", sa.String(length=14), nullable=True),
    )
    op.create_index(
        "ix_loan_applications_rles_unq_no",
        "loan_applications",
        ["rles_unq_no"],
    )


def downgrade() -> None:
    op.drop_index("ix_loan_applications_rles_unq_no", table_name="loan_applications")
    op.drop_column("loan_applications", "rles_unq_no")
