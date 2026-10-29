"""Production on Render: required environment, PostgreSQL, HTTPS and WhiteNoise."""
import os
from urllib.parse import urlsplit
from django.core.exceptions import ImproperlyConfigured
from .settings import *  # noqa: F403
from .database import postgres_database

DEBUG = False
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5 or SECRET_KEY.startswith("django-insecure-"):
    raise ImproperlyConfigured("Configure DJANGO_SECRET_KEY con una clave aleatoria fuerte de al menos 50 caracteres.")
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]
render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
if render_host:
    ALLOWED_HOSTS.append(render_host)
ALLOWED_HOSTS = list(dict.fromkeys(ALLOWED_HOSTS))
if not ALLOWED_HOSTS or any(h == "*" or "/" in h or ":" in h or h.startswith(".") for h in ALLOWED_HOSTS):
    raise ImproperlyConfigured("Configure hosts explícitos, sin esquema, puerto ni comodines.")
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get("DJANGO_CSRF_ORIGINS", "").split(",") if o.strip()]
if render_host:
    CSRF_TRUSTED_ORIGINS.append("https://" + render_host)
CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(CSRF_TRUSTED_ORIGINS))
if not CSRF_TRUSTED_ORIGINS or any(urlsplit(o).scheme != "https" or urlsplit(o).netloc not in ALLOWED_HOSTS or urlsplit(o).path or "*" in o or urlsplit(o).query or urlsplit(o).fragment for o in CSRF_TRUSTED_ORIGINS):
    raise ImproperlyConfigured("Configure orígenes HTTPS exactos correspondientes a ALLOWED_HOSTS, sin barra final.")
DATABASES = {"default": postgres_database(os.environ.get("DATABASE_URL", ""))}
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
X_FRAME_OPTIONS = "DENY"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
STATIC_URL = "/static/"
STORAGES = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}}
WHITENOISE_KEEP_ONLY_HASHED_FILES = True
KAWA_PUBLIC_DEMO = os.environ.get("KAWA_PUBLIC_DEMO", "false").lower() == "true"
