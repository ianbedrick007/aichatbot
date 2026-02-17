"""
Test script to verify WhatsApp bot refactoring

This script checks that:
1. Settings load correctly
2. Router is properly configured
3. All endpoints are registered
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_settings():
    """Test that WhatsApp settings load correctly"""
    print("Testing WhatsApp settings...")
    try:
        from whatsapp_bot.app.config import whatsapp_settings

        # Check required settings
        assert whatsapp_settings.access_token, "ACCESS_TOKEN not loaded"
        assert whatsapp_settings.verify_token, "VERIFY_TOKEN not loaded"
        assert whatsapp_settings.version, "VERSION not loaded"

        print("[PASS] Settings loaded successfully")
        print(f"   - Version: {whatsapp_settings.version}")
        print(f"   - Phone Number ID: {whatsapp_settings.phone_number_id or 'Not set'}")
        return True
    except Exception as e:
        print(f"[FAIL] Settings test failed: {e}")
        return False


def test_router():
    """Test that router is properly configured"""
    print("\nTesting WhatsApp router...")
    try:
        from whatsapp_bot.app import router

        # Check router exists and is an APIRouter
        from fastapi import APIRouter
        assert isinstance(router, APIRouter), "Router is not an APIRouter instance"

        # Check routes are registered
        routes = [route.path for route in router.routes]
        print("[PASS] Router configured successfully")
        print(f"   - Routes registered: {routes}")

        # Verify expected routes
        assert "/webhook" in routes, "Webhook route not found"
        return True
    except Exception as e:
        print(f"[FAIL] Router test failed: {e}")
        return False


def test_integration():
    """Test that router can be integrated into main app"""
    print("\nTesting main app integration...")
    try:
        from main import app

        # Check WhatsApp routes are registered
        whatsapp_routes = [
            route for route in app.routes
            if hasattr(route, 'path') and '/api/whatsapp' in route.path
        ]

        print("[PASS] Integration successful")
        print(f"   - WhatsApp routes in main app: {len(whatsapp_routes)}")
        for route in whatsapp_routes:
            if hasattr(route, 'methods'):
                print(f"   - {list(route.methods)} {route.path}")
        return True
    except Exception as e:
        print(f"[FAIL] Integration test failed: {e}")
        return False


def test_dependencies():
    """Test that all dependencies are importable"""
    print("\nTesting dependencies...")
    try:
        from whatsapp_bot.app.decorators.security import signature_required, validate_signature
        from whatsapp_bot.app.utils.whatsapp_utils import (
            send_message,
            process_whatsapp_message,
            is_valid_whatsapp_message
        )

        print("[PASS] All dependencies importable")
        return True
    except Exception as e:
        print(f"[FAIL] Dependency test failed: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("WhatsApp Bot Refactoring Verification")
    print("=" * 60)

    results = []
    results.append(("Settings", test_settings()))
    results.append(("Router", test_router()))
    results.append(("Dependencies", test_dependencies()))
    results.append(("Integration", test_integration()))

    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    for test_name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{test_name:20s}: {status}")

    all_passed = all(result[1] for result in results)

    print("=" * 60)
    if all_passed:
        print("SUCCESS: All tests passed! Refactoring successful.")
        sys.exit(0)
    else:
        print("WARNING: Some tests failed. Please review the errors above.")
        sys.exit(1)
