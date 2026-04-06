"""Add GLG-style tables: project_categories, screener_questions, expert_profiles, expert_activities, linkedin_outreach

Revision ID: d001_add_glg_tables
Revises: c1234567_add_followup_fields
Create Date: 2026-04-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = "d001_add_glg_tables"
down_revision = "c1234567_add_followup_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add headline and photo_url to candidates
    op.add_column("candidates", sa.Column("headline", sa.String(), nullable=True))
    op.add_column("candidates", sa.Column("photo_url", sa.String(), nullable=True))

    # Create enum types
    op.execute("CREATE TYPE screenerquestiontype AS ENUM ('multiple_choice', 'free_text', 'yes_no', 'scale')")
    op.execute("CREATE TYPE expertprofilestatus AS ENUM ('sourced', 'screened', 'shortlisted', 'scheduled', 'completed', 'rejected')")
    op.execute("CREATE TYPE expertactivitytype AS ENUM ('added', 'call_requested', 'call_scheduled', 'call_completed', 'email_sent', 'reply_received', 'linkedin_sent', 'linkedin_connected')")
    op.execute("CREATE TYPE linkedinoutreachstatus AS ENUM ('pending', 'connection_sent', 'connected', 'message_sent', 'replied', 'failed')")

    # Project Categories
    op.create_table(
        "project_categories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("project_briefs.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("search_criteria", JSON, server_default="{}"),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    # Screener Questions
    op.create_table(
        "screener_questions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("project_briefs.id"), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("question_type", sa.Enum("multiple_choice", "free_text", "yes_no", "scale", name="screenerquestiontype", create_type=False), nullable=False),
        sa.Column("options", JSON, server_default="[]"),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    # Expert Profiles
    op.create_table(
        "expert_profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("candidate_id", UUID(as_uuid=True), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("project_briefs.id"), nullable=False),
        sa.Column("category_id", UUID(as_uuid=True), sa.ForeignKey("project_categories.id"), nullable=True),
        sa.Column("ai_overview", sa.Text()),
        sa.Column("project_expertise", JSON, server_default="[]"),
        sa.Column("relevance_score", sa.Float()),
        sa.Column("rate_per_hour", sa.Numeric(10, 2)),
        sa.Column("exa_research", JSON, server_default="{}"),
        sa.Column("screener_responses", JSON, server_default="{}"),
        sa.Column("work_experience", JSON, server_default="[]"),
        sa.Column("status", sa.Enum("sourced", "screened", "shortlisted", "scheduled", "completed", "rejected", name="expertprofilestatus", create_type=False), nullable=False, server_default="sourced"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime()),
    )
    op.create_index("ix_expert_profile_candidate_project", "expert_profiles", ["candidate_id", "project_id"])
    op.create_index("ix_expert_profile_category", "expert_profiles", ["category_id"])

    # Expert Activities
    op.create_table(
        "expert_activities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("expert_profile_id", UUID(as_uuid=True), sa.ForeignKey("expert_profiles.id"), nullable=False),
        sa.Column("activity_type", sa.Enum("added", "call_requested", "call_scheduled", "call_completed", "email_sent", "reply_received", "linkedin_sent", "linkedin_connected", name="expertactivitytype", create_type=False), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    # LinkedIn Outreach
    op.create_table(
        "linkedin_outreach",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("expert_profile_id", UUID(as_uuid=True), sa.ForeignKey("expert_profiles.id"), nullable=False),
        sa.Column("linkedin_url", sa.String(), nullable=False),
        sa.Column("connection_note", sa.String(300)),
        sa.Column("follow_up_message", sa.Text()),
        sa.Column("status", sa.Enum("pending", "connection_sent", "connected", "message_sent", "replied", "failed", name="linkedinoutreachstatus", create_type=False), nullable=False, server_default="pending"),
        sa.Column("sent_at", sa.DateTime()),
        sa.Column("connected_at", sa.DateTime()),
        sa.Column("replied_at", sa.DateTime()),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("linkedin_outreach")
    op.drop_table("expert_activities")
    op.drop_table("expert_profiles")
    op.drop_table("screener_questions")
    op.drop_table("project_categories")
    op.drop_column("candidates", "photo_url")
    op.drop_column("candidates", "headline")
    op.execute("DROP TYPE IF EXISTS linkedinoutreachstatus")
    op.execute("DROP TYPE IF EXISTS expertactivitytype")
    op.execute("DROP TYPE IF EXISTS expertprofilestatus")
    op.execute("DROP TYPE IF EXISTS screenerquestiontype")
