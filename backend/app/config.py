from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    # Database
    database_url: str = "postgresql://postgres:postgres@postgres:5432/expert_outreach"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Security
    api_key: str = "dev-api-key-change-in-production"
    webhook_secret: str = "dev-webhook-secret-change-in-production"

    # Email Provider (Resend - recommended)
    resend_api_key: str = ""
    resend_from_email: str = "outreach@arcticblue.com"
    resend_from_name: str = "Arctic Blue Research"

    # Email Provider (SendGrid - legacy)
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = "outreach@arcticblue.com"
    sendgrid_from_name: str = "Arctic Blue Research"
    sendgrid_webhook_verification_key: str = ""  # For SendGrid signed webhooks
    sendgrid_inbound_domain: str = ""  # e.g., parse.yourdomain.com

    # LLM (Claude)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-sonnet-20241022"

    # Apollo.io (People Search / Enrichment)
    apollo_api_key: str = ""

    # App
    environment: str = "development"
    log_level: str = "INFO"

    # Rate Limiting
    rate_limit_per_domain_per_hour: int = 10
    rate_limit_jitter_min_seconds: int = 5
    rate_limit_jitter_max_seconds: int = 30


settings = Settings()
