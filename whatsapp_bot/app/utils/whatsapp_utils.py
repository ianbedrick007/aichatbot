import base64
import logging
import re
import time

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ai.run_ai import get_ai_response, get_conversation_history, update_conversation_history, clear_conversation_history
from models import Business
from ..config import whatsapp_settings

# Global set to store users who have AI disabled
AI_DISABLED_USERS = set()

# Global cache to store processed message IDs for deduplication
PROCESSED_MESSAGE_IDS = {}


def toggle_ai_status(wa_id: str, enable: bool):
    if enable:
        if wa_id in AI_DISABLED_USERS:
            AI_DISABLED_USERS.remove(wa_id)
    else:
        AI_DISABLED_USERS.add(wa_id)


def log_http_response(response):
    logging.info(f"Status: {response.status_code}")
    logging.info(f"Content-type: {response.headers.get('content-type')}")
    logging.info(f"Body: {response.text}")


def get_text_message_input(recipient: str, text: str):
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "text",
        "text": {"preview_url": False, "body": text},
    }


def generate_response(response):
    # Return text in uppercase
    return response.upper()


async def send_message(data: dict, phone_number_id: str = None, access_token: str = None):
    """Send a message via WhatsApp Business API"""
    # Use provided credentials or fallback to settings
    phone_id = phone_number_id or whatsapp_settings.phone_number_id
    token = access_token or whatsapp_settings.access_token.get_secret_value()

    url = f"https://graph.facebook.com/{whatsapp_settings.version}/{phone_id}/messages"

    headers = {
        "Content-type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=data, headers=headers, timeout=10)
            response.raise_for_status()
    except httpx.TimeoutException:
        logging.error("Timeout occurred while sending message")
        return None
    except httpx.RequestError as e:
        logging.error(f"Request failed: {e}")
        return None

    log_http_response(response)
    return response


def process_text_for_whatsapp(text: str):
    # Remove 【...】
    text = re.sub(r"\【.*?\】", "", text).strip()

    # Convert **bold** → *bold*
    text = re.sub(r"\*\*(.*?)\*\*", r"*\1*", text)

    return text


async def get_media_url(media_id):
    """Get the URL for the media file from WhatsApp API"""
    url = f"https://graph.facebook.com/{whatsapp_settings.version}/{media_id}"
    headers = {
        "Authorization": f"Bearer {whatsapp_settings.access_token.get_secret_value()}",
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json().get("url")


async def download_media(media_url):
    """Download media file and return as base64 string"""
    headers = {
        "Authorization": f"Bearer {whatsapp_settings.access_token.get_secret_value()}",
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(media_url, headers=headers)
        response.raise_for_status()
        return base64.b64encode(response.content).decode("utf-8")


async def send_typing_indicator(message_id: str, phone_number_id: str, access_token: str = None):
    """
    Send a typing indicator and mark the message as read.
    """
    data = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
        "typing_indicator": {
            "type": "text"
        }
    }
    await send_message(data, phone_number_id=phone_number_id, access_token=access_token)


async def process_whatsapp_message(body, db: AsyncSession):
    """
    Process incoming WhatsApp message and link it to the correct business.
    """
    # from models import db  # Import here to avoid circular imports

    # Safe extraction of contact info
    contact = body["entry"][0]["changes"][0]["value"]["contacts"][0]
    wa_id = contact.get("wa_id")
    name = contact.get("profile", {}).get("name", wa_id)  # Fallback to ID if name missing

    message = body["entry"][0]["changes"][0]["value"]["messages"][0]
    message_id = message.get("id")

    # Deduplication: Check if message_id was already processed
    if message_id:
        current_time = time.time()
        # Cleanup: Remove IDs older than 5 minutes (300 seconds)
        for mid in list(PROCESSED_MESSAGE_IDS.keys()):
            if current_time - PROCESSED_MESSAGE_IDS[mid] > 300:
                del PROCESSED_MESSAGE_IDS[mid]

        if message_id in PROCESSED_MESSAGE_IDS:
            logging.info(f"Skipping duplicate message ID: {message_id}")
            return
        PROCESSED_MESSAGE_IDS[message_id] = current_time

    message_type = message.get("type")

    image_data = None
    media_url = None
    message_body = ""

    if message_type == "text":
        message_body = message["text"]["body"]
    elif message_type == "image":
        media_id = message["image"]["id"]
        try:
            media_url = await get_media_url(media_id)
            image_data = await download_media(media_url)
            # Use caption as text, or default prompt
            message_body = message["image"].get("caption") or "Please analyze this image."
        except Exception as e:
            logging.error(f"Error processing image: {e}")
            message_body = "I sent an image but there was an error processing it."
    else:
        # Ignore other message types (audio, video, etc.) for now
        return

    # ✅ Get the PHONE_NUMBER_ID from the webhook payload
    phone_number_id = body["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"]

    # ✅ Find the business associated with this phone number
    result = await db.execute(
        select(Business)
        .where(Business.phone_number_id == phone_number_id
               ))
    business = result.scalars().first()

    if not business:
        logging.error(f"No business found for phone_number_id: {phone_number_id}")
        # Send error message back to user
        error_response = "Sorry, this WhatsApp number is not configured for any business."
        data = get_text_message_input(wa_id, error_response)
        await send_message(data, phone_number_id=phone_number_id)
        return
        # ✅ Send typing indicator
    await send_typing_indicator(
        message_id=message_id,
        phone_number_id=phone_number_id,
        access_token=whatsapp_settings.access_token.get_secret_value()
    )
    logging.info(f"Processing message for business: {business.name} (ID: {business.id})")

    # ✅ Save incoming user message to database
    await update_conversation_history(
        business_id=business.id,
        text=message_body,
        sender=wa_id,
        customer_id=wa_id,
        customer_name=name,
        is_bot=False,
        db=db,
        platform="whatsapp"
    )

    # ✅ Check if AI is enabled for this user
    if name in AI_DISABLED_USERS or wa_id in AI_DISABLED_USERS:
        logging.info(f"AI response disabled for user {name}. Skipping AI generation.")
        return

    # ✅ Get recent messages for context (isolated by customer)
    conversation_history = await get_conversation_history(business.id, wa_id, customer_name=None, db=db)

    # ✅ Get AI response with business context
    if message_body.lower() == "refresh":
        await clear_conversation_history(db, business_id=business.id, sender=name)
        response = "History refreshed. How can I help you today?"
    else:
        response = await get_ai_response(message_body, db, conversation_history, business_id=business.id, user_name=name,
                                         image_data=image_data, image_url=media_url)

    # Process for WhatsApp formatting
    response = process_text_for_whatsapp(response)

    # Send response back to user
    data = get_text_message_input(wa_id, response)
    await send_message(data, phone_number_id=phone_number_id)

    # ✅ Save bot response to database
    await update_conversation_history(
        business_id=business.id,
        text=response,
        sender='bot',
        customer_id=wa_id,
        customer_name=name,
        is_bot=True,
        db=db,
        platform="whatsapp"
    )


def is_valid_whatsapp_message(body):
    """
    Check if the incoming webhook event has a valid WhatsApp message structure.
    """
    return (
            body.get("object")
            and body.get("entry")
            and body["entry"][0].get("changes")
            and body["entry"][0]["changes"][0].get("value")
            and body["entry"][0]["changes"][0]["value"].get("messages")
            and body["entry"][0]["changes"][0]["value"]["messages"][0]
    )
