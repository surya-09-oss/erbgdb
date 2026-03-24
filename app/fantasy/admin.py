"""Admin API — simple token-based auth for managing fantasy players."""

import os
import secrets
from typing import Optional

# Admin token: set via ADMIN_TOKEN env var, or auto-generated at startup
ADMIN_TOKEN: str = os.environ.get("ADMIN_TOKEN", secrets.token_urlsafe(32))


def verify_admin_token(token: Optional[str]) -> bool:
    """Verify admin token. Returns True if valid."""
    if not token:
        return False
    return secrets.compare_digest(token, ADMIN_TOKEN)
