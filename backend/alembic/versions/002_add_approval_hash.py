"""add approval hash

Revision ID: 002
Revises: 001
Create Date: 2026-02-04

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('message_drafts', sa.Column('approved_hash', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('message_drafts', 'approved_hash')
