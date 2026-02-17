import logging
import base64
import re

import requests
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ai.run_ai import get_ai_response, get_conversation_history, update_conversation_history, clear_conversation_history
from models import Business
from ..config import whatsapp_settings

# Global set to store users who have AI disabled
AI_DISABLED_USERS = set()


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


def send_message(data: dict):
    """Send a message via WhatsApp Business API"""
    url = f"https://graph.facebook.com/{whatsapp_settings.version}/{whatsapp_settings.phone_number_id}/messages"

    headers = {
        "Content-type": "application/json",
        "Authorization": f"Bearer {whatsapp_settings.access_token.get_secret_value()}",
    }

    try:
        response = requests.post(url, json=data, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.Timeout:
        logging.error("Timeout occurred while sending message")
        return None
    except requests.RequestException as e:
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


def get_media_url(media_id):
    """Get the URL for the media file from WhatsApp API"""
    url = f"https://graph.facebook.com/{whatsapp_settings.version}/{media_id}"
    headers = {
        "Authorization": f"Bearer {whatsapp_settings.access_token.get_secret_value()}",
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json().get("url")


def download_media(media_url):
    """Download media file and return as base64 string"""
    headers = {
        "Authorization": f"Bearer {whatsapp_settings.access_token.get_secret_value()}",
    }
    response = requests.get(media_url, headers=headers)
    response.raise_for_status()
    return base64.b64encode(response.content).decode("utf-8")


def process_whatsapp_message(body, db: Session):
    """
    Process incoming WhatsApp message and link it to the correct business.
    """
    # from models import db  # Import here to avoid circular imports

    # Safe extraction of contact info
    contact = body["entry"][0]["changes"][0]["value"]["contacts"][0]
    wa_id = contact.get("wa_id")
    name = contact.get("profile", {}).get("name", wa_id) # Fallback to ID if name missing

    message = body["entry"][0]["changes"][0]["value"]["messages"][0]
    message_type = message.get("type")

    image_data = None
    message_body = ""

    if message_type == "text":
        message_body = message["text"]["body"]
    elif message_type == "image":
        media_id = message["image"]["id"]
        try:
            media_url = get_media_url(media_id)
            image_data = download_media(media_url)
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
    business = db.query(Business).filter(Business.phone_number_id == phone_number_id).first()

    if not business:
        logging.error(f"No business found for phone_number_id: {phone_number_id}")
        # Send error message back to user
        error_response = "Sorry, this WhatsApp number is not configured for any business."
        data = get_text_message_input(wa_id, error_response)
        send_message(data)
        return

    logging.info(f"Processing message for business: {business.name} (ID: {business.id})")

    # ✅ Save incoming user message to database
    update_conversation_history(
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
    conversation_history = get_conversation_history(business.id, wa_id, db)

    # ✅ Get AI response with business context
    if message_body.lower() == "refresh":
        clear_conversation_history(db, business_id=business.id, sender=name)
        conversation_history = []
        response = "History refreshed. How can I help you today?"
    else:
        response = get_ai_response(message_body, db, conversation_history, business_id=business.id, user_name=name, image_data=image_data)

    # ✅ Save bot response to database
    update_conversation_history(
        business_id=business.id, 
        text=response, 
        sender='bot', 
        customer_id=wa_id,
        customer_name=name,
        is_bot=True,
        db=db,
        platform="whatsapp"
    )

    # Process for WhatsApp formatting
    response = process_text_for_whatsapp(response)

    # Send response back to user
    data = get_text_message_input(wa_id, response)
    send_message(data)


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
