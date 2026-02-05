"""Add rejection_learnings table

Revision ID: 003
Revises: 002
Create Date: 2026-02-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'rejection_learnings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('candidate_title', sa.String(), nullable=True),
        sa.Column('candidate_company', sa.String(), nullable=True),
        sa.Column('rejected_subject', sa.String(), nullable=False),
        sa.Column('rejected_body', sa.Text(), nullable=False),
        sa.Column('inferred_issues', postgresql.JSON(), default=list),
        sa.Column('rejected_by', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['project_briefs.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_rejection_learning_project', 'rejection_learnings', ['project_id'])


def downgrade():
    op.drop_index('ix_rejection_learning_project', table_name='rejection_learnings')
    op.drop_table('rejection_learnings')
