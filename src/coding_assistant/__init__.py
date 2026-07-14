"""Coding assistant package.

The .env file is loaded here, on package import, so configuration is in
place before any module reads it (web.py builds the agent at import time).
"""

from dotenv import load_dotenv

load_dotenv(override=True)
