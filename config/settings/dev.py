"""Local development settings: debug on, throwaway secrets, compose Postgres."""

from .base import *  # noqa: F403

DEBUG = True

# Dev-only key; never reused anywhere real.
SECRET_KEY = "django-insecure-dev-only-key-not-for-production"  # noqa: S105  # nosec B105

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "tracker",
        "USER": "tracker",
        "PASSWORD": "devpass",  # nosec B105 — matches docker-compose.yml, dev-only
        "HOST": "localhost",
        "PORT": "5433",  # compose maps 5433 -> 5432 (local PG service owns 5432)
    }
}
