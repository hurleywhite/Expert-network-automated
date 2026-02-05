"""initial schema

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None

# Define ENUM types once; create_type=False prevents auto-creation during table create
candidatestatus = postgresql.ENUM(
    'new', 'enriched', 'drafted', 'approved', 'sent', 'replied', 'do_not_contact',
    name='candidatestatus',
    create_type=False,
)
outboundeventstatus = postgresql.ENUM(
    'queued', 'sent', 'bounced', 'failed',
    name='outboundeventstatus',
    create_type=False,
)
conversationstatus = postgresql.ENUM(
    'none', 'interested', 'not_interested', 'referral', 'ooo', 'unsubscribe', 'unknown',
    name='conversationstatus',
    create_type=False,
)
messagedirection = postgresql.ENUM(
    'inbound', 'outbound',
    name='messagedirection',
    create_type=False,
)


def upgrade() -> None:
    # Create enum types exactly once
    bind = op.get_bind()
    candidatestatus.create(bind, checkfirst=True)
    outboundeventstatus.create(bind, checkfirst=True)
    conversationstatus.create(bind, checkfirst=True)
    messagedirection.create(bind, checkfirst=True)

    # project_briefs
    op.create_table(
        'project_briefs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('industry', sa.String()),
        sa.Column('subvertical', sa.String()),
        sa.Column('company_size_min', sa.Integer()),
        sa.Column('regions', postgresql.JSON(), default=list),
        sa.Column('titles_include', postgresql.JSON(), default=list),
        sa.Column('titles_exclude', postgresql.JSON(), default=list),
        sa.Column('keywords', postgresql.JSON(), default=list),
        sa.Column('exclusions', postgresql.JSON(), default=list),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    # candidates
    op.create_table(
        'candidates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('first_name', sa.String()),
        sa.Column('last_name', sa.String()),
        sa.Column('full_name', sa.String(), nullable=False),
        sa.Column('title', sa.String()),
        sa.Column('company', sa.String()),
        sa.Column('company_employee_count', sa.Integer()),
        sa.Column('region', sa.String()),
        sa.Column('linkedin_url', sa.String()),
        sa.Column('email', sa.String()),
        sa.Column('email_verified', sa.Boolean(), default=False),
        sa.Column('status', candidatestatus, nullable=False, default='new'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime()),
        sa.UniqueConstraint('email', name='uq_candidate_email'),
    )
    op.create_index('ix_candidate_status', 'candidates', ['status'])
    op.create_index('ix_candidate_company', 'candidates', ['company'])
    op.create_index('ix_candidate_email', 'candidates', ['email'])

    # candidate_sources
    op.create_table(
        'candidate_sources',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('candidate_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('candidates.id'), nullable=False),
        sa.Column('source_name', sa.String(), nullable=False),
        sa.Column('source_url', sa.String()),
        sa.Column('source_payload', postgresql.JSON()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    # enrichments
    op.create_table(
        'enrichments',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('candidate_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('candidates.id'), nullable=False),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('payload', postgresql.JSON()),
        sa.Column('confidence', sa.Float()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    # scores
    op.create_table(
        'scores',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('candidate_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('candidates.id'), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('project_briefs.id'), nullable=False),
        sa.Column('hard_pass', sa.Boolean(), default=False, nullable=False),
        sa.Column('score', sa.Float()),
        sa.Column('reasons', postgresql.JSON(), default=list),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_score_candidate_project', 'scores', ['candidate_id', 'project_id'])

    # message_drafts
    op.create_table(
        'message_drafts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('candidate_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('candidates.id'), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('project_briefs.id'), nullable=False),
        sa.Column('subject', sa.String(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('facts_used', postgresql.JSON(), default=list),
        sa.Column('risk_flags', postgresql.JSON(), default=list),
        sa.Column('approved_at', sa.DateTime()),
        sa.Column('approved_by', sa.String()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    # outbound_events
    op.create_table(
        'outbound_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('message_draft_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('message_drafts.id'), nullable=False),
        sa.Column('candidate_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('candidates.id'), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('project_briefs.id'), nullable=False),
        sa.Column('provider_message_id', sa.String()),
        sa.Column('idempotency_key', sa.String(), nullable=False),
        sa.Column('status', outboundeventstatus, nullable=False, default='queued'),
        sa.Column('meta', postgresql.JSON()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('idempotency_key', name='uq_outbound_idempotency_key'),
    )

    # conversations
    op.create_table(
        'conversations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('candidate_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('candidates.id'), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('project_briefs.id'), nullable=False),
        sa.Column('last_status', conversationstatus, nullable=False, default='none'),
        sa.Column('updated_at', sa.DateTime()),
    )

    # conversation_messages
    op.create_table(
        'conversation_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('conversations.id'), nullable=False),
        sa.Column('direction', messagedirection, nullable=False),
        sa.Column('from_addr', sa.String(), nullable=False),
        sa.Column('to_addr', sa.String(), nullable=False),
        sa.Column('subject', sa.String()),
        sa.Column('body_text', sa.Text()),
        sa.Column('raw_payload', postgresql.JSON()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    # do_not_contact
    op.create_table(
        'do_not_contact',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('reason', sa.String()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('email', name='uq_do_not_contact_email'),
    )

    # audit_log
    op.create_table(
        'audit_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('actor', sa.String(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('entity_type', sa.String(), nullable=False),
        sa.Column('entity_id', sa.String(), nullable=False),
        sa.Column('meta', postgresql.JSON()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_audit_log_entity', 'audit_log', ['entity_type', 'entity_id'])
    op.create_index('ix_audit_log_actor', 'audit_log', ['actor'])


def downgrade() -> None:
    op.drop_table('audit_log')
    op.drop_table('do_not_contact')
    op.drop_table('conversation_messages')
    op.drop_table('conversations')
    op.drop_table('outbound_events')
    op.drop_table('message_drafts')
    op.drop_table('scores')
    op.drop_table('enrichments')
    op.drop_table('candidate_sources')
    op.drop_table('candidates')
    op.drop_table('project_briefs')

    bind = op.get_bind()
    messagedirection.drop(bind, checkfirst=True)
    conversationstatus.drop(bind, checkfirst=True)
    outboundeventstatus.drop(bind, checkfirst=True)
    candidatestatus.drop(bind, checkfirst=True)
