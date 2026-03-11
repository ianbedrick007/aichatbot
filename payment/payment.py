import hashlib
import hmac
import logging
import os
import uuid

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db

load_dotenv()

logger = logging.getLogger(__name__)

AI_BASE_URL = os.getenv("AI_BASE_URL")
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
router = APIRouter()


async def create_order(customer_name: str, amount: float, db: AsyncSession, business_id: int, status: str = "pending"):
    """
    Create a new order for a business.
    """
    try:
        if not db or not business_id:
            logger.error("Database session or business ID missing")
            return {"error": "Database session and business ID required"}

        from models import Order

        # FIX: Use UUID for guaranteed unique Paystack references
        unique_id = uuid.uuid4().hex[:8].upper()
        reference = f"ORD-{unique_id}"

        new_order = Order(
            business_id=business_id,
            customer_name=customer_name,
            amount=amount,
            status=status,
            reference=reference
        )
        db.add(new_order)
        await db.commit()
        await db.refresh(new_order)
        logger.info(f"Order created successfully: ID {new_order.id} for business {business_id}")
        return new_order

    except Exception as e:
        logger.exception(f"Error creating order: {str(e)}")
        return {"error": str(e)}


async def initialize_payment(customer_email, customer_name, business_id: int, db: AsyncSession, amount,
                             callback_url=None, currency="GHS", **kwargs):
    """
    Initialize a transaction with Paystack.
    Amount should be in the smallest currency unit (e.g., pesewas or kobo).
    """
    order = await create_order(customer_name, amount, db, business_id)

    # FIX: Check if order creation failed before proceeding
    if isinstance(order, dict) and "error" in order:
        return order  # Return the error dictionary back to the AI/Client

    url = "https://api.paystack.co/transaction/initialize"
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "email": customer_email,
        "amount": int(float(amount) * 100),  # Cast to float first to prevent math errors with decimals
        "currency": currency,
        "reference": order.reference,  # Safely access the attribute now
        "callback_url": callback_url or f"{AI_BASE_URL}/paystack/callback"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        # FIX: Inject the actual generated reference from the database order
        data['local_reference'] = order.reference
        return data

    except Exception as e:
        # FIX: Return the generated reference even on failure so you can track the abandoned DB order
        return {"error": str(e), "local_reference": order.reference}


async def update_order_status(reference: str, status: str, db: AsyncSession):
    """
    Update the status of an order. (Keep this as an internal helper function, not an AI tool)
    """
    try:
        from models import Order
        result = await db.execute(select(Order).where(Order.reference == reference))
        order = result.scalars().first()

        if not order:
            return {"error": f"Order with reference '{reference}' not found."}

        order.status = status
        await db.commit()
        await db.refresh(order)
        return {
            "message": "Order status updated successfully",
            "reference": order.reference,
            "new_status": order.status
        }
    except Exception as e:
        return {"error": str(e)}


async def verify_payment(reference: str, db: AsyncSession):
    """
    Verify a transaction using Paystack and automatically update the order status.
    This is the only verification tool the AI needs.
    """
    url = f"https://api.paystack.co/transaction/verify/{reference}"
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            paystack_data = response.json()

        # Safely extract the actual transaction status from Paystack's payload
        api_status = paystack_data.get("status")
        tx_status = paystack_data.get("data", {}).get("status")

        if api_status is True and tx_status == "success":
            # Payment is confirmed! Update the DB automatically.
            db_update = await update_order_status(reference, "paid", db)

            if "error" in db_update:
                return {"error": f"Payment verified with Paystack, but DB update failed: {db_update['error']}"}

            return {
                "success": True,
                "message": "Payment verified and order officially marked as paid.",
                "reference": reference
            }
        else:
            # Payment failed, was abandoned, or is still processing
            return {
                "success": False,
                "message": f"Payment has not been completed. Current status: {tx_status}"
            }

    except Exception as e:
        return {"error": str(e)}


@router.get("/paystack/callback")
async def paystack_callback(request: Request, db: AsyncSession = Depends(get_db)):
    reference = request.query_params.get("reference")

    if not reference:
        return {"error": "No reference provided"}

    # Pass the DB session to our upgraded function
    result = await verify_payment(reference, db)

    # Check our simplified boolean return
    if result.get("success"):
        # The database is ALREADY updated at this point!
        # TODO: trigger WhatsApp confirmation via Omni
        return {"message": "Payment verified successfully", "reference": reference}

    return {"message": "Payment not successful", "details": result.get("message")}


@router.post('/paystack-webhook')
async def paystack_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    # 1. Signature Verification
    payload = await request.body()
    paystack_signature = request.headers.get('x-paystack-signature')

    if not paystack_signature:
        raise HTTPException(status_code=400, detail="Missing signature header")

    computed_signature = hmac.new(
        PAYSTACK_SECRET_KEY.encode('utf-8'),
        payload,
        hashlib.sha512
    ).hexdigest()

    if computed_signature != paystack_signature:
        raise HTTPException(status_code=401, detail="Invalid signature")

    # 2. Extract the event
    event_data = await request.json()

    if event_data.get('event') == 'charge.success':
        reference = event_data['data']['reference']

        # 3. Verify with Paystack API & Auto-Update DB
        # Calling verify_payment here ensures the DB is marked 'paid' securely
        result = await verify_payment(reference, db)

        # 4. Final check
        if result.get('success'):
            print(f"Transaction {reference} is officially verified via Webhook!")

            # Since Paystack returns the customer info in the webhook, you can extract it here
            customer_phone = event_data['data']['customer'].get('phone')

            # TODO: trigger Omni to send WhatsApp thank you message

            return {"status": "success"}

    # Return a 200 OK so Paystack knows you received it, even if ignored
    return {"status": "ignored"}
