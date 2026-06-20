#!/usr/bin/env python3
"""Test script to check for import errors"""

print("Testing imports...")

try:
    print("1. Testing core imports...")
    from core.constants import *

    print("   ✓ core.constants")

    from core.keyboards import get_main_menu_keyboard

    print("   ✓ core.keyboards")

    from core.state_manager import get_state

    print("   ✓ core.state_manager")

    print("\n2. Testing handlers imports...")
    from handlers.menus.image_processing import (
        btn_image_processing_menu,
        btn_img_create_pdf_req,
        btn_img_convert_format_req,
        btn_img_resize_req,
        btn_img_remove_bg_req,
    )

    print("   ✓ handlers.menus.image_processing")

    from handlers.states.state_image_processing import (
        handle_img_create_pdf,
        handle_img_convert_format,
        handle_img_resize,
        handle_img_remove_bg,
    )

    print("   ✓ handlers.states.state_image_processing")

    print("\n3. Testing handlers.__init__...")
    from handlers import register_all_handlers

    print("   ✓ handlers.__init__")

    print("\n✅ All imports successful!")
    print("\nNow testing main.py...")

except Exception as e:
    print(f"\n❌ Import error: {e}")
    import traceback

    traceback.print_exc()

# Made with Bob
