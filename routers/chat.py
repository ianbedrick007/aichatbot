from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from datetime import datetime, timezone
from sqlalchemy import delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ai.run_ai import get_ai_response
from database import get_db, get_current_user
from models import Business, User, Message
from schemas import ChatRequest

router = APIRouter()


@router.post("/clear-session")
async def clear_session(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Delete all messages associated with a specific business."""

    # Fetch business
    results = await db.execute(
        select(Business).where(Business.user_id == current_user.id)
    )
    business = results.scalar_one_or_none()

    if not business:
        raise HTTPException(status_code=400, detail="No business found for this account.")

    # Delete web platform messages for this business
    result = await db.execute(
        delete(Message).where(
            Message.business_id == business.id,
            Message.platform == "web"
        )
    )
    print(f"{result.rowcount} messages were deleted by user")
    await db.commit()
    return RedirectResponse(url="/chat", status_code=status.HTTP_303_SEE_OTHER)

    

@router.post("/api/chat", tags=["chat"])
async def api_chat_post(
        request: ChatRequest,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    # Fetch business
    results = await db.execute(
        select(Business).where(Business.user_id == current_user.id)
    )
    business = results.scalar_one_or_none()

    if not business:
        raise HTTPException(status_code=400, detail="No business found for this account.")

    user_message = request.message.strip()

    if user_message:
        # Get last 20 messages for context
        result = await db.execute(
            select(Message)
            .where(
                Message.business_id == business.id,
                Message.platform == "web"
            )
            .order_by(Message.timestamp.desc())
            .limit(20)
        )

        recent_messages = result.scalars().all()

        conversation_history = [
            {"text": msg.text, "sender": msg.sender, "is_bot": msg.is_bot}
            for msg in reversed(recent_messages)
        ]

        # Save user message
        user_msg = Message(
            business_id=business.id,
            text=user_message,
            sender="user",
            is_bot=False,
            platform="web",
            timestamp=datetime.now(timezone.utc).replace(tzinfo=None)
        )
        db.add(user_msg)
        await db.commit()

        # AI response
        bot_response = await get_ai_response(user_message, db, conversation_history, business_id=business.id)

        if not bot_response or not bot_response.strip():
            bot_response = "I'm sorry, I couldn't generate a response."

        # Save bot message
        bot_msg = Message(
            business_id=business.id,
            text=bot_response,
            sender="bot",
            is_bot=True,
            platform="web",
            timestamp=datetime.now(timezone.utc).replace(tzinfo=None)
        )
        db.add(bot_msg)
        await db.commit()

        return {"response": bot_response}
    return {"response": "I didn't catch that."}
