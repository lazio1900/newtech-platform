"""create oracle_etl_mappings — Oracle→PG ETL 테이블/컬럼 매핑(관리자 편집)

Revision ID: 0018
Revises: 0017
"""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oracle_etl_mappings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("internal_table", sa.String(length=64), nullable=False),
        sa.Column("oracle_table", sa.String(length=128), nullable=False),
        sa.Column("column_overrides", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("internal_table", name="uq_oracle_etl_mappings_internal_table"),
    )


def downgrade() -> None:
    op.drop_table("oracle_etl_mappings")
