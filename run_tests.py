#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_tests.py — Automated Test Runner for น้องเพชร AI Smart Guide
สั่งรันการทดสอบทั้งหมดในโฟลเดอร์ tests/ และสรุปผลการทดสอบ
"""
import unittest
import sys
import os

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

def main():
    print("=" * 65)
    print("🧪 น้องเพชร AI Smart Guide — Automated Test Suite")
    print("=" * 65)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    test_dir = os.path.join(base_dir, 'tests')

    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=test_dir, pattern='test_*.py')

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 65)
    print(f"📊 สรุปผลการทดสอบ: รันทั้งหมด {result.testsRun} รายการ")
    if result.wasSuccessful():
        print("✅ การทดสอบทั้งหมดผ่านเรียบร้อย (ALL TESTS PASSED)!")
        return 0
    else:
        print(f"❌ มีข้อผิดพลาด {len(result.errors)} รายการ, ล้มเหลว {len(result.failures)} รายการ")
        return 1

if __name__ == '__main__':
    sys.exit(main())

