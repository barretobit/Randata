"""Admin protection for the finance endpoints."""

import hmac
from typing import Optional

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from ...config import ADMIN_KEY

_admin_key_header = APIKeyHeader(name="X-Admin-Key", scheme_name="X-Admin-Key", auto_error=False)


def require_admin(admin_key: Optional[str] = Security(_admin_key_header)) -> None:
    """Allow the request only with the right X-Admin-Key header.

    Fails closed: when ADMIN_KEY is not configured, every admin endpoint is disabled.
    """
    if not ADMIN_KEY:
        raise HTTPException(
            status_code=503, detail="Admin endpoints are disabled: ADMIN_KEY is not configured."
        )
    if admin_key is None or not hmac.compare_digest(admin_key.encode("utf-8"), ADMIN_KEY.encode("utf-8")):
        raise HTTPException(status_code=403, detail="Invalid admin key.")
