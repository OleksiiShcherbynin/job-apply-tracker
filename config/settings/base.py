"""Settings shared by every environment. dev.py / prod.py override the rest."""

from pathlib import Path

# base.py -> settings -> config -> project root
BASE_DIR = Path(__file__).resolve().parent.parent.parent

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "drf_spectacular",
    # local apps
    "accounts",
    "tracker",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Serves collected static files from gunicorn; no separate web server needed.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # Language from the switch's cookie only; the browser's preference is ignored.
    "config.locale.CookieLocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # Site-wide templates (base layout, auth pages) that belong to no app.
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Custom user model; must exist before the first migration of any app.
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("sk", "Slovenčina"), ("ru", "Русский")]
# Catalogs are committed (.po and compiled .mo): the dev machine has no GNU
# gettext, docker/i18n.sh regenerates them in a throwaway container.
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "Europe/Bratislava"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "tracker:dashboard"
LOGOUT_REDIRECT_URL = "login"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    # The API is machine-to-machine: token only, no session/basic auth, and
    # nothing is open unless a view says so (the schema views do).
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.TokenAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # One daily batch plus retries is a handful of requests; this is generous.
    "DEFAULT_THROTTLE_RATES": {"user": "60/hour"},
}

SPECTACULAR_SETTINGS = {
    "TITLE": "job-apply-tracker API",
    "DESCRIPTION": "Ingest of scored vacancies pushed by job-ai-assist.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}
