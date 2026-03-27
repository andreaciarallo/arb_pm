"""
Root conftest.py — adds src/ to sys.path so pytest discovers bot package.

This avoids needing to set PYTHONPATH=src manually when running pytest.
"""
import sys
import os

# Add src/ to path so `from bot.xxx import yyy` works without PYTHONPATH
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
