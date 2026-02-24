from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from database import get_db, get_current_user
from models import User, Message

router = APIRouter(tags=["Conversations"])


class ToggleAIRequest(BaseModel):
    customer_id: str
    enable_ai: bool
    message: str | None = None


@router.get("/api/customers")
def get_customers(
        db: Session = Depends(get_db),
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

    results = db.execute(stmt).all()

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
            "ai_enabled": True  # Default to True as we don't have a Customer model yet
        })

    return {"customers": customers}


@router.get("/api/customer-messages/{customer_id}")
def get_customer_messages(
        customer_id: str,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    business = current_user.business
    if not business:
        return {"messages": []}

    msgs = db.execute(
        select(Message)
        .where(Message.business_id == business.id)
        .where(Message.customer_id == customer_id)
        .order_by(Message.timestamp)
    ).scalars().all()

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
def toggle_ai(
        request: ToggleAIRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    # Logic to toggle AI would go here.
    # For now, we just acknowledge the request.
    return {"status": "success", "ai_enabled": request.enable_ai}
