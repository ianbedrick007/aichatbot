from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, get_current_user
from models import User, Message
from ai.run_ai import update_conversation_history
from whatsapp_bot.app.config import whatsapp_settings
from whatsapp_bot.app.utils.whatsapp_utils import toggle_ai_status, get_text_message_input, send_message, AI_DISABLED_USERS

router = APIRouter(tags=["Conversations"])


class ToggleAIRequest(BaseModel):
    customer_id: str
    enable_ai: bool
    message: str | None = None


@router.get("/api/customers")
async def get_customers(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    business = current_user.business
    if not business:
        return {"customers": []}

    # Subquery to find the latest timestamp for each customer
    latest_msg_subq = (
        select(
            Message.customer_id,
            func.max(Message.timestamp).label("max_ts")
        )
        .where(Message.business_id == business.id)
        .where(Message.customer_id.isnot(None))
        .group_by(Message.customer_id)
        .subquery()
    )

    # Subquery to count messages per customer
    count_subq = (
        select(
            Message.customer_id,
            func.count(Message.id).label("msg_count")
        )
        .where(Message.business_id == business.id)
        .where(Message.customer_id.isnot(None))
        .group_by(Message.customer_id)
        .subquery()
    )

    # Main query: Join Message with subqueries to get details of the latest message + count
    stmt = (
        select(Message, count_subq.c.msg_count)
        .join(latest_msg_subq,
              (Message.customer_id == latest_msg_subq.c.customer_id) &
              (Message.timestamp == latest_msg_subq.c.max_ts)
              )
        .join(count_subq, Message.customer_id == count_subq.c.customer_id)
        .where(Message.business_id == business.id)
        .order_by(Message.timestamp.desc())
    )

    result = await db.execute(stmt)
    results = result.all()

    customers = []
    for row in results:
        msg = row[0]
        count = row[1]
        customers.append({
            "id": msg.customer_id,
            "name": msg.customer_name or msg.customer_id,
            "last_message": msg.text,
            "last_timestamp": msg.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "message_count": count,
            "ai_enabled": msg.customer_id not in AI_DISABLED_USERS
        })

    return {"customers": customers}


@router.get("/api/customer-messages/{customer_id}")
async def get_customer_messages(
        customer_id: str,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    business = current_user.business
    if not business:
        return {"messages": []}

    result = await db.execute(
        select(Message)
        .where(Message.business_id == business.id)
        .where(Message.customer_id == customer_id)
        .order_by(Message.timestamp)
    )
    msgs = result.scalars().all()

    return {
        "messages": [
            {
                "text": m.text,
                "timestamp": m.timestamp.strftime("%H:%M"),
                "is_bot": m.is_bot
            } for m in msgs
        ]
    }


@router.post("/api/toggle-ai")
async def toggle_ai(
        request: ToggleAIRequest,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    business = current_user.business
    if not business:
        raise HTTPException(status_code=400, detail="User has no business")

    # Toggle AI status
    toggle_ai_status(request.customer_id, request.enable_ai)

    # If a message is provided, send it via WhatsApp
    if request.message:
        data = get_text_message_input(request.customer_id, request.message)
        await send_message(
            data,
            phone_number_id=business.phone_number_id,
            access_token=whatsapp_settings.access_token.get_secret_value()
        )

        # Save the manual message to conversation history
        await update_conversation_history(
            business_id=business.id,
            text=request.message,
            sender="agent",
            customer_id=request.customer_id,
            customer_name=request.customer_id,  # Fallback to ID if name is unknown
            is_bot=True,
            db=db,
            platform="whatsapp"
        )

    return {"status": "success", "ai_enabled": request.enable_ai}
