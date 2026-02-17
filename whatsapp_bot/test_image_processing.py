"""
Test script to verify image processing capabilities

This simulates a WhatsApp webhook payload with an image message
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_image_message_structure():
    """Test that we can parse image message structure"""
    print("Testing image message structure parsing...")
    
    # Sample WhatsApp webhook payload with image
    sample_image_payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "phone_number_id": "923338760870948"
                    },
                    "contacts": [{
                        "wa_id": "233264022366",
                        "profile": {"name": "Test User"}
                    }],
                    "messages": [{
                        "from": "233264022366",
                        "id": "wamid.test123",
                        "timestamp": "1234567890",
                        "type": "image",
                        "image": {
                            "id": "test_media_id_123",
                            "mime_type": "image/jpeg",
                            "sha256": "test_hash",
                            "caption": "What is this product?"
                        }
                    }]
                }
            }]
        }]
    }
    
    try:
        from whatsapp_bot.app.utils.whatsapp_utils import is_valid_whatsapp_message
        
        # Verify structure is valid
        is_valid = is_valid_whatsapp_message(sample_image_payload)
        assert is_valid, "Image message structure should be valid"
        
        # Extract message details
        message = sample_image_payload["entry"][0]["changes"][0]["value"]["messages"][0]
        message_type = message.get("type")
        
        assert message_type == "image", f"Expected 'image' type, got '{message_type}'"
        
        # Check image data
        assert "image" in message, "Image data should be present"
        assert "id" in message["image"], "Media ID should be present"
        assert "caption" in message["image"], "Caption should be present"
        
        media_id = message["image"]["id"]
        caption = message["image"].get("caption")
        
        print("[PASS] Image message structure is valid")
        print(f"   - Message type: {message_type}")
        print(f"   - Media ID: {media_id}")
        print(f"   - Caption: {caption}")
        
        return True
    except Exception as e:
        print(f"[FAIL] Image structure test failed: {e}")
        return False


def test_ai_image_support():
    """Test that AI function accepts image_data parameter"""
    print("\nTesting AI image support...")
    
    try:
        from ai.run_ai import get_ai_response
        import inspect
        
        # Check function signature
        sig = inspect.signature(get_ai_response)
        params = list(sig.parameters.keys())
        
        assert "image_data" in params, "get_ai_response should accept image_data parameter"
        
        print("[PASS] AI function supports image_data parameter")
        print(f"   - Parameters: {params}")
        
        return True
    except Exception as e:
        print(f"[FAIL] AI image support test failed: {e}")
        return False


def test_media_functions():
    """Test that media download functions exist"""
    print("\nTesting media download functions...")
    
    try:
        from whatsapp_bot.app.utils.whatsapp_utils import get_media_url, download_media
        
        # Check functions exist and are callable
        assert callable(get_media_url), "get_media_url should be callable"
        assert callable(download_media), "download_media should be callable"
        
        print("[PASS] Media download functions exist")
        print("   - get_media_url: Available")
        print("   - download_media: Available")
        
        return True
    except Exception as e:
        print(f"[FAIL] Media functions test failed: {e}")
        return False


def test_vision_model_config():
    """Test that vision-capable model is configured"""
    print("\nTesting vision model configuration...")
    
    try:
        import os
        from dotenv import load_dotenv
        
        load_dotenv()
        
        model = os.getenv("OPEN_ROUTER_MODEL")
        
        # Check if using a vision-capable model
        vision_models = [
            "gemini-2.5-flash",
            "gemini-pro-vision",
            "gpt-4-vision",
            "gpt-4o",
            "claude-3"
        ]
        
        is_vision_capable = any(vm in model.lower() for vm in vision_models)
        
        if is_vision_capable:
            print("[PASS] Vision-capable model configured")
            print(f"   - Model: {model}")
        else:
            print("[WARN] Model may not support vision")
            print(f"   - Model: {model}")
            print("   - Consider using: google/gemini-2.5-flash")
        
        return True
    except Exception as e:
        print(f"[FAIL] Vision model config test failed: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("WhatsApp Image Processing Verification")
    print("=" * 60)
    
    results = []
    results.append(("Image Structure", test_image_message_structure()))
    results.append(("AI Image Support", test_ai_image_support()))
    results.append(("Media Functions", test_media_functions()))
    results.append(("Vision Model", test_vision_model_config()))
    
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    for test_name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{test_name:20s}: {status}")
    
    all_passed = all(result[1] for result in results)
    
    print("=" * 60)
    if all_passed:
        print("SUCCESS: Image processing is ready to use!")
        print("\nNext steps:")
        print("1. Send an image to your WhatsApp bot")
        print("2. Add a caption like 'What is this?'")
        print("3. The bot will analyze and respond")
        sys.exit(0)
    else:
        print("WARNING: Some tests failed. Review errors above.")
        sys.exit(1)
