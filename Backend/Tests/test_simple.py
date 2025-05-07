"""
تست‌های ساده بدون نیاز به وابستگی‌های خارجی
"""

def test_addition():
    """
    تست ساده جمع دو عدد
    """
    assert 1 + 1 == 2

def test_subtraction():
    """
    تست ساده تفریق دو عدد
    """
    assert 3 - 1 == 2

def test_multiplication():
    """
    تست ساده ضرب دو عدد
    """
    assert 2 * 3 == 6

def test_division():
    """
    تست ساده تقسیم دو عدد
    """
    assert 6 / 3 == 2

def test_failing():
    """
    تست شکست خورده برای نمایش خروجی pytest
    """
    assert 1 + 1 == 3, "این تست باید شکست بخورد" 