import uuid
from typing import Optional

from fastapi import Response, Cookie


async def get_session_id(
        response: Response,
        session_id: Optional[str] = Cookie(None)
) -> str:
    """
    Dependency to get or create a session ID.
    If no session_id cookie exists, it generates one and sets the cookie.
    """
    if not session_id:
        session_id = str(uuid.uuid4())
        # Set cookie with appropriate security settings
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            max_age=86400,  # 24 hours
            samesite="lax"
        )
    return session_id
