FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements/base.txt requirements/base.txt
RUN pip install -r requirements/base.txt

COPY . .

# Static files are collected into the image at build time; the secret here is a
# throwaway that only exists for this build step.
RUN DJANGO_SETTINGS_MODULE=config.settings.prod \
    DJANGO_SECRET_KEY=build-only DJANGO_ALLOWED_HOSTS=localhost \
    POSTGRES_DB=x POSTGRES_USER=x POSTGRES_PASSWORD=x POSTGRES_HOST=x \
    python manage.py collectstatic --noinput

RUN useradd --uid 10001 --create-home app \
    && mkdir -p /data/media \
    && chown -R app:app /data /app \
    && chmod +x docker/entrypoint.sh
USER app

EXPOSE 8000
ENTRYPOINT ["docker/entrypoint.sh"]
