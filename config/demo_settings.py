"""Configuración local de demostración, separada de db.sqlite3."""
import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
from .settings import *  # noqa: F403

KAWA_DEMO = True
ruta_demo = Path(os.environ.get("KAWA_DEMO_DB_PATH", str(BASE_DIR / "demo.sqlite3"))).resolve()
if ruta_demo == (BASE_DIR / "db.sqlite3").resolve():
    raise ImproperlyConfigured("La demostración no puede usar db.sqlite3. Elija un archivo separado.")
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ruta_demo}}
# Una sesión local de la demo no debe reutilizar la cookie de la base habitual.
SESSION_COOKIE_NAME = "kawa_demo_sessionid"
CSRF_COOKIE_NAME = "kawa_demo_csrftoken"
