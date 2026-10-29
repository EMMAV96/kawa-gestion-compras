"""PostgreSQL URL parsing; never falls back to SQLite or prints credentials."""
from urllib.parse import urlsplit, unquote, parse_qs
from django.core.exceptions import ImproperlyConfigured


def postgres_database(url, require_tls=True):
    try:
        parts = urlsplit(url)
        query = parse_qs(parts.query, strict_parsing=True)
        if parts.scheme not in ("postgres", "postgresql") or not parts.hostname or not parts.username or not parts.password or not parts.path.strip("/") or parts.fragment:
            raise ValueError
        if set(query) - {"sslmode", "channel_binding"} or any(len(v) != 1 for v in query.values()):
            raise ValueError
        sslmode = query.get("sslmode", ["require" if require_tls else "disable"])[0]
        if sslmode not in ({"require", "verify-ca", "verify-full"} if require_tls else {"disable", "require", "verify-ca", "verify-full"}):
            raise ValueError
        options = {"sslmode": sslmode, "connect_timeout": 10}
        if "channel_binding" in query:
            if query["channel_binding"][0] not in {"require", "prefer"}:
                raise ValueError
            options["channel_binding"] = query["channel_binding"][0]
        return {"ENGINE": "django.db.backends.postgresql", "NAME": unquote(parts.path[1:]),
            "USER": unquote(parts.username), "PASSWORD": unquote(parts.password),
            "HOST": parts.hostname, "PORT": parts.port or 5432, "CONN_MAX_AGE": 60,
            "CONN_HEALTH_CHECKS": True, "OPTIONS": options}
    except (ValueError, TypeError, AttributeError):
        raise ImproperlyConfigured("DATABASE_URL debe ser una URL PostgreSQL válida con usuario, clave, base y TLS permitido.") from None
