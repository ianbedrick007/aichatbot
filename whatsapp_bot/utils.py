import logging

import aiohttp

logger = logging.getLogger(__name__)


async def mark_message_as_read(message_id: str, business_phone_number_id: str, access_token: str):
    """
    Mark a WhatsApp message as read to indicate processing (blue ticks).
    Call this immediately after receiving a webhook message.
    """
    url = f"https://graph.facebook.com/v18.0/{business_phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status != 200:
                    logger.error(f"Failed to mark message as read: {await response.text()}")
    except Exception as e:
        logger.error(f"Error marking message as read: {e}")


async def send_typing_indicator(recipient_id: str, business_phone_number_id: str, access_token: str):
    """
    Send a typing indicator to the user to show processing.
    The indicator automatically turns off when a message is sent.
    """
    url = f"https://graph.facebook.com/v18.0/{business_phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": recipient_id,
        "type": "sender_action",
        "sender_action": "typing_on"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status != 200:
                    logger.error(f"Failed to send typing indicator: {await response.text()}")
    except Exception as e:
        logger.error(f"Error sending typing indicator: {e}")
