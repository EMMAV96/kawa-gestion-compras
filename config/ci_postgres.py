"""Only for automated tests against an isolated PostgreSQL server, never live data."""
import os
from .settings import *  # noqa: F403
from .database import postgres_database
DATABASES = {"default": postgres_database(os.environ.get("DATABASE_URL", ""), require_tls=False)}
DATABASES["default"]["CONN_MAX_AGE"] = 0

KAWA_TEST_DEMO = True  # Only the isolated test_* database created by Django.
