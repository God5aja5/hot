#!/usr/bin/env python3
"""
Test the retry logic in Xbox checker.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from xbox_checker import XboxChecker

def test_retry_logic():
    """Test that retry logic works correctly"""
    print("Testing Xbox checker retry logic...")
    
    # Create a checker with verbose mode
    checker = XboxChecker(verbose=True)
    
    # Test with a dummy account that will likely fail
    # This tests the error retry logic
    print("\n1. Testing error retry logic...")
    result1 = checker.check_account("invalid@example.com", "wrongpassword")
    print(f"   Result status: {result1.get('status')}")
    print(f"   Stats - Retries: {checker.stats.retries}")
    print(f"   Stats - Retry Success: {checker.stats.retry_success}")
    print(f"   Stats - Retry Failed: {checker.stats.retry_failed}")
    
    # Test with another account
    print("\n2. Testing another account...")
    result2 = checker.check_account("another@example.com", "password123")
    print(f"   Result status: {result2.get('status')}")
    print(f"   Stats - Retries: {checker.stats.retries}")
    print(f"   Stats - Retry Success: {checker.stats.retry_success}")
    print(f"   Stats - Retry Failed: {checker.stats.retry_failed}")
    
    # Print final stats
    print("\n3. Final statistics:")
    print(f"   Total checked: {checker.stats.checked}")
    print(f"   Errors: {checker.stats.errors}")
    print(f"   Retries attempted: {checker.stats.retries}")
    print(f"   Retry successful: {checker.stats.retry_success}")
    print(f"   Retry failed: {checker.stats.retry_failed}")
    
    # Test the stats methods
    print(f"\n4. Performance metrics:")
    print(f"   CPM: {checker.stats.get_cpm()}")
    print(f"   Elapsed time: {checker.stats.get_elapsed_time()}")
    
    return True

def main():
    print("=" * 60)
    print("Xbox Checker Retry Logic Test")
    print("=" * 60)
    
    try:
        test_retry_logic()
        
        print("\n" + "=" * 60)
        print("✅ Retry logic test completed!")
        print("=" * 60)
        print("\nNote: The test uses invalid credentials, so expect:")
        print("  - Most accounts will return 'BAD' or 'ERROR'")
        print("  - Some errors will be retried (1/3 chance)")
        print("  - Retry statistics should be tracked")
        
        return 0
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())