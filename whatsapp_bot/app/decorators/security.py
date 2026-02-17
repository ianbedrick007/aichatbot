import hashlib
import hmac

from fastapi import Request, HTTPException

from ..config import whatsapp_settings


def validate_signature(payload: str, signature: str) -> bool:
    """Validate WhatsApp webhook signature"""
    if not whatsapp_settings.app_secret:
        raise ValueError("APP_SECRET not configured")

    app_secret = whatsapp_settings.app_secret.get_secret_value()

    expected = hmac.new(
        app_secret.encode("utf-8"),
        msg=payload.encode("utf-8"),
        digestmod=hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


async def signature_required(request: Request):
    """FastAPI dependency to validate WhatsApp webhook signatures"""
    # Extract signature header
    header = request.headers.get("X-Hub-Signature-256", "")
    signature = header.replace("sha256=", "")

    # Read raw body
    raw_body = await request.body()
    payload = raw_body.decode("utf-8")

    # Validate
    if not validate_signature(payload, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")
