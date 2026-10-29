#!/usr/bin/env sh
set -eu
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.production}"
if [ "$DJANGO_SETTINGS_MODULE" != "config.production" ]; then
  echo "Production scripts require DJANGO_SETTINGS_MODULE=config.production" >&2
  exit 1
fi
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers 2 --threads 2 --timeout 60 --access-logfile - --error-logfile -
