FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DJANGO_SETTINGS_MODULE=config.production
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home kawa && mkdir -p /app/staticfiles && chown -R kawa:kawa /app
USER kawa
EXPOSE 8000
# After explicit migrations and with runtime environment supplied; never seed accounts.
CMD ["sh", "-c", "python manage.py check --deploy --fail-level ERROR && python manage.py collectstatic --noinput && exec sh start.sh"]
