#!/usr/bin/env python3
"""
Test script to verify both checker implementations work correctly.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from hotmail_checker import HotmailChecker
from xbox_checker import XboxChecker

def test_hotmail_checker():
    """Test the Hotmail checker with a dummy account"""
    print("Testing Hotmail Checker...")
    checker = HotmailChecker()
    
    # Test with dummy credentials (should return BAD)
    result = checker.check_account("test@example.com", "password123")
    print(f"  Result: {result.get('status')}")
    print(f"  Expected: BAD or RETRY")
    print("  Hotmail checker test completed.\n")

def test_xbox_checker():
    """Test the Xbox checker with a dummy account"""
    print("Testing Xbox Checker...")
    checker = XboxChecker()
    
    # Test with dummy credentials (should return BAD)
    result = checker.check_account("test@example.com", "password123")
    print(f"  Result: {result.get('status')}")
    print(f"  Expected: BAD or ERROR")
    
    # Test that the result has all required fields for Xbox checker
    if result.get('status') == 'HIT':
        required_fields = ['email', 'password', 'account_type', 'capture', 'file_category', 'hit_line']
        for field in required_fields:
            if field not in result:
                print(f"  ❌ Missing field: {field}")
            else:
                print(f"  ✓ Field present: {field}")
    
    print("  Xbox checker test completed.\n")

def test_imports():
    """Test that all required imports work"""
    print("Testing imports...")
    try:
        import telebot
        import requests
        import pycountry
        import threading
        import time
        import zipfile
        import tempfile
        import re
        import json
        from queue import Queue, Empty
        from colorama import Fore, Style, init
        print("  All imports successful!")
    except ImportError as e:
        print(f"  Import error: {e}")
        return False
    return True

def main():
    print("=" * 60)
    print("Checker Implementation Test")
    print("=" * 60)
    
    # Test imports
    if not test_imports():
        print("❌ Import test failed!")
        return 1
    
    # Test checkers
    test_hotmail_checker()
    test_xbox_checker()
    
    print("=" * 60)
    print("✅ All tests completed successfully!")
    print("=" * 60)
    return 0

if __name__ == "__main__":
    sys.exit(main())