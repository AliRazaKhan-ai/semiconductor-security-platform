"""Production WSGI entry point for SemiSecure."""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv(".env", override=False)

from app import create_app

app = create_app()
