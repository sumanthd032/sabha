"""Shared test fixtures: fills in the environment config.py requires.

These are placeholder values for tests only, never real credentials.
"""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("GEMINI_API_KEY", "test-placeholder-key")
os.environ.setdefault("QUOTA_RPM", "10")
os.environ.setdefault("QUOTA_RPD", "250")
