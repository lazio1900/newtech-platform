"""loan_applications: business_number + credit scores (NICE/KCB)

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "loan_applications",
        sa.Column("business_number", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "loan_applications",
        sa.Column("credit_score_nice", sa.Integer(), nullable=True),
    )
    op.add_column(
        "loan_applications",
        sa.Column("credit_score_kcb", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("loan_applications", "credit_score_kcb")
    op.drop_column("loan_applications", "credit_score_nice")
    op.drop_column("loan_applications", "business_number")
