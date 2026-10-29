#!/usr/bin/env bash
set -euo pipefail
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.production}"
if [ "$DJANGO_SETTINGS_MODULE" != "config.production" ]; then
  echo "Production scripts require DJANGO_SETTINGS_MODULE=config.production" >&2
  exit 1
fi
python -m pip install -r requirements.txt
python manage.py check --deploy --fail-level ERROR
python manage.py collectstatic --noinput
