"""Ephemeral credentials for isolated automated tests, never demo accounts."""
import secrets
TEST_PASSWORD = secrets.token_urlsafe(24)
