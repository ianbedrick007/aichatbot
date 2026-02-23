from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.run_ai import get_ai_response
from database import get_db, get_current_user
from models import Business, User, Message
from schemas import ChatRequest

router = APIRouter()


@router.post("/clear-session")
def clear_session():
    pass


@router.post("/api/chat", tags=["chat"])
async def api_chat_post(
        request: ChatRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    # Fetch business
    business = db.execute(
        select(Business).where(Business.user_id == current_user.id)
    ).scalar()

    if not business:
        raise HTTPException(status_code=404, detail="No business found for this account.")

    user_message = request.message.strip()

    if user_message:
        # Get last 20 messages for context
        recent_messages = (
            db.query(Message)
            .filter(Message.business_id == business.id)
            .order_by(Message.timestamp.desc())
            .limit(20)
            .all()
        )

        conversation_history = [
            {"text": msg.text, "sender": msg.sender, "is_bot": msg.is_bot}
            for msg in reversed(recent_messages)
        ]

        # Save user message
        user_msg = Message(business_id=business.id, text=user_message, sender="user", is_bot=False)
        db.add(user_msg)
        db.commit()

        # AI response
        bot_response = get_ai_response(user_message, db, conversation_history, business_id=business.id)

        # Save bot message
        bot_msg = Message(business_id=business.id, text=bot_response, sender="bot", is_bot=True)
        db.add(bot_msg)
        db.commit()

        return {"response": bot_response}
    return {"response": "I didn't catch that."}
