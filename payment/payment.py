import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
import requests
import hmac
import hashlib

load_dotenv()

AI_BASE_URL = os.getenv("AI_BASE_URL")
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
app = FastAPI()


def initialize_payment(customer_email, amount, callback_url=None, currency="GHS",**kwargs):
    """
    Initialize a transaction with Paystack.
    Amount should be in the smallest currency unit (e.g., pesewas or kobo).
    """
    url = "https://api.paystack.co/transaction/initialize"
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "email": customer_email,
        "amount": int(amount * 100),  # Convert to smallest unit
        "currency": currency,
        "callback_url": callback_url or f"{AI_BASE_URL}/paystack/callback"
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def verify_payment(reference):
    """
    Verify a transaction using the reference provided by Paystack.
    """
    url = f"https://api.paystack.co/transaction/verify/{reference}"
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}


@app.get("/paystack/callback")
async def paystack_callback(request: Request):
    reference = request.query_params.get("reference")

    if not reference:
        return {"error": "No reference provided"}

    data = verify_payment(reference)

    if data.get("status") and data["data"]["status"] == "success":
        # TODO: update your database
        # TODO: trigger WhatsApp confirmation
        return {"message": "Payment verified successfully", "reference": reference}

    return {"message": "Payment not successful", "details": data}


@app.post('/paystack-webhook')
async def paystack_webhook(request: Request):
    # 1. Signature Verification
    payload = await request.body()
    paystack_signature = request.headers.get('x-paystack-signature')

    computed_signature = hmac.new(
        PAYSTACK_SECRET_KEY.encode('utf-8'),
        payload,
        hashlib.sha512
    ).hexdigest()

    if computed_signature != paystack_signature:
        raise HTTPException(status_code=401, detail="Invalid signature")

    # 2. Extract the reference from the webhook data
    event_data = await request.json()

    if event_data.get('event') == 'charge.success':
        reference = event_data['data']['reference']
        expected_amount = event_data['data']['amount']

        # 3. Verify with Paystack API
        verify_data = verify_payment(reference)

        # 4. Final check
        if verify_data.get('status') and verify_data['data']['status'] == 'success':
            actual_amount = verify_data['data']['amount']

            if actual_amount == expected_amount:
                print(f"Transaction {reference} is officially verified!")
                # TODO: send_whatsapp_thank_you(user_phone)
                return {"status": "success"}

    return {"status": "ignored"}