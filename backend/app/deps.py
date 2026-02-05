from typing import Generator

from fastapi import Depends, HTTPException, Header, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db


def verify_api_key(x_api_key: str = Header(...)) -> str:
    """Verify API key for protected endpoints"""
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return x_api_key


def verify_webhook_secret(x_webhook_secret: str = Header(...)) -> str:
    """Verify webhook secret"""
    if x_webhook_secret != settings.webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook secret",
        )
    return x_webhook_secret
