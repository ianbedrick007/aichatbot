from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.run_ai import update_conversation_history
from database import get_db, get_current_user
from models import Business, User, Message
from schemas import ToggleAIRequest
from whatsapp_bot.app.utils.whatsapp_utils import AI_DISABLED_USERS, toggle_ai_status, get_text_message_input, \
    send_message

router = APIRouter()


@router.get("/api/live-messages")
def get_live_messages(
        request: Request,
        after_id: int = Query(0),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    business = db.execute(select(Business).where(Business.user_id == current_user.id)).scalar()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # ✅ Fetch only WHATSAPP messages newer than 'after_id'
    new_messages = (
        db.query(Message)
        .filter(Message.business_id == business.id)
        .filter(Message.id > after_id)
        .filter(Message.platform == 'whatsappp')  # <--- STRICT FILTER
        .order_by(Message.id.asc())
        .limit(50)
        .all()
    )

    return {
        "messages": [
            {
                "id": msg.id,
                "text": msg.text,
                "sender": msg.sender,
                "timestamp": msg.timestamp.strftime("%H:%M"),
                "is_bot": msg.sender == 'bot'
            }
            for msg in new_messages
        ]
    }


@router.get("/api/customers", tags=["conversations"])
def get_customers_list(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Retrieve a list of unique WhatsApp customers for the current business.

    Args:
        db (Session): The database session.
        current_user (User): The currently authenticated user.

    Returns:
        JSONResponse: A list of customers with their latest message details and AI status.
    """
    business = db.execute(select(Business).where(Business.user_id == current_user.id)).scalar()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # Get all WhatsApp messages for this business
    whatsrouter_messages = (
        db.query(Message)
        .filter(Message.business_id == business.id)
        .filter(Message.platform == 'whatsapp')
        .order_by(Message.timestamp.desc())
        .all()
    )

    # Group by unique customer ID
    customers = {}
    for msg in whatsrouter_messages:
        c_id = msg.customer_id
        if not c_id: continue

        if c_id not in customers:
            customers[c_id] = {
                "id": c_id,
                "name": msg.customer_name or c_id,
                "last_message": msg.text[:50] + "..." if msg.text and len(msg.text) > 50 else (msg.text or ""),
                "last_timestamp": msg.timestamp.strftime("%Y-%m-%d %H:%M"),
                "message_count": 1,
                "ai_enabled": c_id not in AI_DISABLED_USERS
            }
        else:
            customers[c_id]["message_count"] += 1

    payload = {"customers": list(customers.values())}

    return JSONResponse(content=payload)


@router.get("/api/customer-messages/{customer_name}", tags=["conversations"])
def get_customer_messages(
        customer_name: str,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Retrieve the full message history for a specific WhatsApp customer.

    Args:
        customer_name (str): The unique identifier (phone number/WhatsApp ID) of the customer.
        db (Session): The database session.
        current_user (User): The currently authenticated user.

    Returns:
        dict: A dictionary containing the customer identifier and a list of message objects
              including text, sender, timestamp, and bot status.
    """
    business = db.execute(select(Business).where(Business.user_id == current_user.id)).scalar()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # Get all messages (both customer and bot) for this specific conversation
    messages = (
        db.query(Message)
        .filter(Message.business_id == business.id)
        .filter(Message.platform == 'whatsrouter')
        .filter(Message.customer_id == customer_name)  # customer_name route param is actually c_id/wa_id
        .order_by(Message.timestamp.asc())
        .all()
    )

    payload = {
        "customer_name": customer_name,
        "messages": [
            {
                "id": msg.id,
                "text": msg.text,
                "sender": msg.customer_name if not msg.is_bot else "bot",
                "timestamp": msg.timestamp.strftime("%H:%M"),
                "is_bot": msg.is_bot
            }
            for msg in messages
        ]
    }
    return JSONResponse(content=payload)


@router.post("/api/toggle-ai", tags=["chat"])
def api_toggle_ai(
        request: ToggleAIRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Toggle the AI response status for a specific customer and optionally send a manual message.

    Args:
        request (ToggleAIRequest): The request body containing customer_id, enable_ai flag, and optional message.
        db (Session): The database session.
        current_user (User): The currently authenticated user.

    Returns:
        JSONResponse: A success status and the updated AI state.
    """
    # Fetch business to ensure context
    business = db.execute(
        select(Business).where(Business.user_id == current_user.id)
    ).scalar()

    if not business:
        raise HTTPException(status_code=404, detail="No business found")

    # Update the AI status
    toggle_ai_status(request.customer_id, request.enable_ai)

    # If disabling AI and a message is provided, send it
    if not request.enable_ai and request.message:
        # Send to WhatsApp
        data = get_text_message_input(request.customer_id, request.message)
        response = send_message(data)

        if not response:
            raise HTTPException(status_code=400,
                                detail="Failed to send WhatsApp message. The customer ID might be invalid (names are not allowed, only phone numbers).")

        # Save to database so it routerears in the chat history
        # Since we don't have the profile name here, we'll try to find it from previous messages or use ID
        prev_msg = db.query(Message).filter_by(customer_id=request.customer_id).first()
        customer_name = prev_msg.customer_name if prev_msg else request.customer_id

        update_conversation_history(
            db=db,
            business_id=business.id,
            text=request.message,
            sender='bot',
            customer_id=request.customer_id,
            customer_name=customer_name,
            is_bot=True,
            platform='whatsapp'
        )

    payload = {"status": "success", "ai_enabled": request.enable_ai}

    return JSONResponse(content=payload)
