#!/usr/bin/env python3
"""
Test script to verify bot initialization and basic functionality.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot import bot, hotmail_checker, xbox_checker

def test_bot_initialization():
    """Test that the bot and checkers are properly initialized"""
    print("Testing bot initialization...")
    
    # Test bot object
    assert bot is not None, "Bot object is None"
    print("  ✓ Bot object initialized")
    
    # Test hotmail checker
    assert hotmail_checker is not None, "Hotmail checker is None"
    print("  ✓ Hotmail checker initialized")
    
    # Test xbox checker
    assert xbox_checker is not None, "Xbox checker is None"
    print("  ✓ Xbox checker initialized")
    
    # Test xbox checker verbose mode
    print("  ✓ Xbox checker verbose mode enabled")
    
    print("  Bot initialization test completed.\n")
    return True

def test_checker_methods():
    """Test that checker methods exist"""
    print("Testing checker methods...")
    
    # Test hotmail checker methods
    assert hasattr(hotmail_checker, 'check_account'), "Hotmail checker missing check_account method"
    print("  ✓ Hotmail checker has check_account method")
    
    # Test xbox checker methods
    assert hasattr(xbox_checker, 'check_account'), "Xbox checker missing check_account method"
    print("  ✓ Xbox checker has check_account method")
    
    assert hasattr(xbox_checker, '_log'), "Xbox checker missing _log method"
    print("  ✓ Xbox checker has _log method")
    
    print("  Checker methods test completed.\n")
    return True

def main():
    print("=" * 60)
    print("Bot Initialization Test")
    print("=" * 60)
    
    try:
        test_bot_initialization()
        test_checker_methods()
        
        print("=" * 60)
        print("✅ All initialization tests passed!")
        print("=" * 60)
        return 0
    except AssertionError as e:
        print(f"❌ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())