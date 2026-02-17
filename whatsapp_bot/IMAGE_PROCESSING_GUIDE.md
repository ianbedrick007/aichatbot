# WhatsApp Image Processing Guide

## Overview

Your WhatsApp bot now supports **image analysis** using Google's Gemini 2.5 Flash vision model. Users can send images through WhatsApp, and the AI will analyze and respond to them.

---

## 🎯 How It Works

### 1. **User Sends Image**
When a user sends an image via WhatsApp:
- The image can include an optional caption
- WhatsApp sends the image metadata to your webhook

### 2. **Image Download & Processing**
Your bot automatically:
1. Extracts the `media_id` from the WhatsApp webhook
2. Calls WhatsApp API to get the media URL
3. Downloads the image using your access token
4. Converts the image to base64 format

### 3. **AI Vision Analysis**
The image is sent to Gemini 2.5 Flash:
- Image is embedded in the message as base64 data
- AI analyzes the image content
- AI responds based on the image and any caption/context

### 4. **Response Sent Back**
The AI's analysis is sent back to the user via WhatsApp

---

## 📋 Current Implementation

### File: `whatsapp_bot/app/utils/whatsapp_utils.py`

#### Image Download Functions

```python
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
```

#### Message Processing with Image Support

```python
def process_whatsapp_message(body, db: Session):
    # Extract message details
    message = body["entry"][0]["changes"][0]["value"]["messages"][0]
    message_type = message.get("type")
    
    image_data = None
    message_body = ""
    
    if message_type == "text":
        message_body = message["text"]["body"]
    
    elif message_type == "image":
        media_id = message["image"]["id"]
        try:
            # Download and encode image
            media_url = get_media_url(media_id)
            image_data = download_media(media_url)
            
            # Use caption as text, or default prompt
            message_body = message["image"].get("caption") or "Please analyze this image."
        except Exception as e:
            logging.error(f"Error processing image: {e}")
            message_body = "I sent an image but there was an error processing it."
    
    # Pass image_data to AI
    response = get_ai_response(
        message_body, 
        db, 
        conversation_history, 
        business_id=business.id, 
        user_name=name, 
        image_data=image_data  # ← Image passed here
    )
```

### File: `ai/run_ai.py`

#### Vision-Enabled AI Response

```python
def get_ai_response(user_input, db, conversation_history=None, 
                   business_id=None, user_name=None, image_data=None):
    """
    Get AI response with conversation context and tool calling.
    
    Args:
        image_data: Optional base64-encoded image data for vision analysis
    """
    
    # Build message with image if provided
    if image_data:
        # For vision models, use content array with text and image
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": user_input},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_data}"
                    }
                }
            ]
        })
    else:
        messages.append({"role": "user", "content": user_input})
    
    # Send to Gemini 2.5 Flash (supports vision)
    completion = client.chat.completions.create(
        model="google/gemini-2.5-flash",  # Vision-capable model
        messages=messages,
        tools=tools,
    )
```

---

## 🚀 Usage Examples

### Example 1: Image with Caption
**User sends:** 📷 Image of a product + Caption: "What is this?"

**Bot receives:**
- `message_type`: "image"
- `message_body`: "What is this?"
- `image_data`: base64-encoded image

**Bot responds:** "This appears to be a [product description based on image analysis]..."

### Example 2: Image without Caption
**User sends:** 📷 Image only

**Bot receives:**
- `message_type`: "image"
- `message_body`: "Please analyze this image."
- `image_data`: base64-encoded image

**Bot responds:** "I can see [detailed description of what's in the image]..."

### Example 3: Text Only
**User sends:** "Hello"

**Bot receives:**
- `message_type`: "text"
- `message_body`: "Hello"
- `image_data`: None

**Bot responds:** "Hello! How can I help you today?"

---

## 🔧 Configuration

### Required Environment Variables

Already configured in your `.env`:

```env
# WhatsApp API
ACCESS_TOKEN=<your_whatsapp_token>
VERSION=v24.0
PHONE_NUMBER_ID=<your_phone_id>

# AI Model (Vision-capable)
OPENROUTER_API_KEY=<your_openrouter_key>
OPEN_ROUTER_MODEL=google/gemini-2.5-flash
```

### Supported Image Formats

WhatsApp supports:
- JPEG
- PNG
- GIF (static)

Maximum file size: **5MB**

---

## 🎨 Customizing Image Analysis

### Modify the Default Prompt

In `whatsapp_utils.py`, line 112:

```python
# Current default
message_body = message["image"].get("caption") or "Please analyze this image."

# Customize for your use case:
message_body = message["image"].get("caption") or "Describe this product in detail."
# or
message_body = message["image"].get("caption") or "Is this item in good condition?"
```

### Add Image-Specific System Prompts

In `ai/run_ai.py`, you can add context when images are present:

```python
if image_data:
    messages.append({
        "role": "system", 
        "content": "You are analyzing an image. Provide detailed, accurate descriptions."
    })
```

---

## 🐛 Error Handling

### Current Error Handling

```python
try:
    media_url = get_media_url(media_id)
    image_data = download_media(media_url)
    message_body = message["image"].get("caption") or "Please analyze this image."
except Exception as e:
    logging.error(f"Error processing image: {e}")
    message_body = "I sent an image but there was an error processing it."
```

### Common Issues

1. **Image Download Fails**
   - **Cause:** Invalid `ACCESS_TOKEN` or expired media URL
   - **Solution:** Check token validity, media URLs expire after a short time

2. **Vision Model Error**
   - **Cause:** Image too large or corrupted
   - **Solution:** WhatsApp compresses images, but check file size limits

3. **No Response**
   - **Cause:** API rate limits or model unavailable
   - **Solution:** Add retry logic or fallback response

---

## 📊 Monitoring

### Log Image Processing

Current logging in place:

```python
logging.info(f"Processing message for business: {business.name} (ID: {business.id})")
logging.error(f"Error processing image: {e}")
```

### Add More Detailed Logging

```python
if message_type == "image":
    logging.info(f"Image received - Media ID: {media_id}")
    logging.info(f"Caption: {message['image'].get('caption', 'None')}")
    logging.info(f"Image size: {len(image_data)} bytes (base64)")
```

---

## 🔮 Future Enhancements

### 1. Support More Media Types

```python
elif message_type == "video":
    # Extract video thumbnail or first frame
    media_id = message["video"]["id"]
    # Process video...

elif message_type == "document":
    # Handle PDF, DOCX, etc.
    media_id = message["document"]["id"]
    # Process document...
```

### 2. Image Storage

Save images for later reference:

```python
import os
from datetime import datetime

def save_image(image_data, business_id, wa_id):
    """Save image to disk for records"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"media/whatsapp_images/{business_id}_{wa_id}_{timestamp}.jpg"
    
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    with open(filename, "wb") as f:
        f.write(base64.b64decode(image_data))
    
    return filename
```

### 3. Image Metadata in Database

Add to your `Message` model:

```python
class Message(Base):
    # ... existing fields
    has_image = Column(Boolean, default=False)
    image_path = Column(String, nullable=True)
    image_caption = Column(String, nullable=True)
```

### 4. Multi-Image Support

Process multiple images in one message:

```python
if message_type == "image":
    images = message.get("images", [message["image"]])  # Support multiple
    image_data_list = []
    
    for img in images:
        media_url = get_media_url(img["id"])
        image_data_list.append(download_media(media_url))
    
    # Pass all images to AI
    response = get_ai_response(..., image_data=image_data_list)
```

---

## ✅ Testing

### Test Image Processing

1. **Send a test image:**
   - Open WhatsApp
   - Send an image to your bot's number
   - Add caption: "What do you see?"

2. **Check logs:**
   ```bash
   # Look for these log entries
   Processing message for business: ...
   Image received - Media ID: ...
   ```

3. **Verify response:**
   - Bot should analyze the image
   - Response should reference image content

### Test Error Handling

1. **Send corrupted image**
   - Should receive: "I sent an image but there was an error processing it."

2. **Send very large image**
   - WhatsApp auto-compresses, but test 5MB+ images

---

## 📚 API References

- [WhatsApp Business API - Media](https://developers.facebook.com/docs/whatsapp/cloud-api/reference/media)
- [OpenRouter - Vision Models](https://openrouter.ai/docs#vision)
- [Gemini 2.5 Flash - Vision Capabilities](https://ai.google.dev/gemini-api/docs/vision)

---

## 🎉 Summary

Your WhatsApp bot now has **full image processing capabilities**:

✅ **Automatic image download** from WhatsApp  
✅ **Base64 encoding** for API transmission  
✅ **Vision AI analysis** using Gemini 2.5 Flash  
✅ **Caption support** for context  
✅ **Error handling** for failed downloads  
✅ **Conversation history** preserved  

**No additional setup required** - it's ready to use! Just send an image to your WhatsApp bot and it will analyze it.

---

**Last Updated:** 2026-02-16  
**Status:** ✅ Fully Implemented and Tested
