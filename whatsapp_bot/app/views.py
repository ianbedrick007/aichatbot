import json
import logging
import os

from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from database import get_db
from .decorators.security import signature_required
from .utils.whatsapp_utils import (
    process_whatsapp_message,
    is_valid_whatsapp_message,
)

router = APIRouter()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")


@router.post("/webhook", tags=["WhatsApp"])
async def webhook_post(
        request: Request,
        db: Session = Depends(get_db),
        _: None = Depends(signature_required)
):
    """
    Handle incoming webhook events from the WhatsApp API.

    WhatsApp sends 4 events per message:
    - message
    - sent
    - delivered
    - read
    """
    try:
        body = await request.json()
    except json.JSONDecodeError:
        logging.error("Failed to decode JSON")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON provided"
        )

    # Check if it's a WhatsApp status update (sent/delivered/read)
    statuses = (
        body.get("entry", [{}])[0]
        .get("changes", [{}])[0]
        .get("value", {})
        .get("statuses")
    )

    if statuses:
        # It's a delivery/read status — acknowledge and exit
        logging.info("Received a WhatsApp status update.")
        return JSONResponse({"status": "ok"}, status_code=200)

    # Handle actual incoming messages
    if is_valid_whatsapp_message(body):
        process_whatsapp_message(body, db)
        return JSONResponse({"status": "ok"}, status_code=200)

    # Not a valid WhatsApp event
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Not a WhatsApp API event"
    )


@router.get("/webhook", tags=["WhatsApp"])
async def webhook_get(request: Request):
    """
    Required webhook verification for WhatsApp.
    
    WhatsApp will send a GET request to verify the webhook endpoint.
    """
    # Parse params from the webhook verification request
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    # Check if a token and mode were sent
    if not mode or not token:
        logging.info("MISSING_PARAMETER")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing parameters"
        )

    # Check the mode and token sent are correct
    if mode == "subscribe" and token == VERIFY_TOKEN:
        # Respond with 200 OK and challenge token from the request
        logging.info("WEBHOOK_VERIFIED")
        return PlainTextResponse(content=challenge, status_code=200)

    # Responds with '403 Forbidden' if verify tokens do not match
    logging.info("VERIFICATION_FAILED")
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Verification failed"
    )
