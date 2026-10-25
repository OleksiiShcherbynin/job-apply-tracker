"""Settings for the always-on container (and, later, a real deployment).

Everything secret or machine-specific comes from the environment and a missing
variable fails loudly (KeyError) at startup instead of running half-configured.
"""

import os

from .base import *  # noqa: F403

DEBUG = False

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

ALLOWED_HOSTS = os.environ["DJANGO_ALLOWED_HOSTS"].split(",")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["POSTGRES_DB"],
        "USER": os.environ["POSTGRES_USER"],
        "PASSWORD": os.environ["POSTGRES_PASSWORD"],
        "HOST": os.environ["POSTGRES_HOST"],
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

MEDIA_ROOT = os.environ.get("DJANGO_MEDIA_ROOT", "/data/media")

# Filled by `collectstatic` at image build; dev serves straight from static/.
STATIC_ROOT = BASE_DIR / "staticfiles"  # noqa: F405

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# HTTPS-only behaviour. On by default; the local laptop container runs plain
# HTTP on localhost and sets DJANGO_HTTPS=0.
HTTPS = os.environ.get("DJANGO_HTTPS", "1") == "1"
SECURE_SSL_REDIRECT = HTTPS
SESSION_COOKIE_SECURE = HTTPS
CSRF_COOKIE_SECURE = HTTPS
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30 if HTTPS else 0
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if HTTPS else None
