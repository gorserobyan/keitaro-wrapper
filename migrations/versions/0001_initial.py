"""initial: campaigns and operations

Revision ID: 0001
Revises:
Create Date: 2026-11-27
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("keitaro_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("alias", sa.String(length=64), nullable=True),
        sa.Column("geo", sa.JSON(), nullable=False),
        sa.Column("geo_stream_id", sa.Integer(), nullable=True),
        sa.Column("offers_stream_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_campaigns_keitaro_id", "campaigns", ["keitaro_id"], unique=True)

    op.create_table(
        "operations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("keitaro_campaign_id", sa.Integer(), nullable=False),
        sa.Column(
            "campaign_id",
            sa.Integer(),
            sa.ForeignKey("campaigns.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_operations_keitaro_campaign_id", "operations", ["keitaro_campaign_id"])


def downgrade() -> None:
    op.drop_index("ix_operations_keitaro_campaign_id", table_name="operations")
    op.drop_table("operations")
    op.drop_index("ix_campaigns_keitaro_id", table_name="campaigns")
    op.drop_table("campaigns")
