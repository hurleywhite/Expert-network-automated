"""Add follow-up fields to message_drafts

Revision ID: c1234567
Revises: b865c63b4cc0
Create Date: 2026-02-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1234567'
down_revision = 'b865c63b4cc0'
branch_labels = None
depends_on = None


def upgrade():
    # Add sequence_number column with default 1
    op.add_column('message_drafts', sa.Column('sequence_number', sa.Integer(), nullable=True))
    op.execute("UPDATE message_drafts SET sequence_number = 1 WHERE sequence_number IS NULL")
    op.alter_column('message_drafts', 'sequence_number', nullable=False)
    
    # Add parent_draft_id for linking follow-ups
    op.add_column('message_drafts', sa.Column('parent_draft_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_message_drafts_parent_draft_id',
        'message_drafts',
        'message_drafts',
        ['parent_draft_id'],
        ['id']
    )


def downgrade():
    op.drop_constraint('fk_message_drafts_parent_draft_id', 'message_drafts', type_='foreignkey')
    op.drop_column('message_drafts', 'parent_draft_id')
    op.drop_column('message_drafts', 'sequence_number')
