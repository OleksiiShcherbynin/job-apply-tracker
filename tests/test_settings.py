import importlib

import pytest
from django.conf import settings

PROD_ENV = {
    "DJANGO_SECRET_KEY": "test-only",
    "DJANGO_ALLOWED_HOSTS": "localhost",
    "POSTGRES_DB": "tracker",
    "POSTGRES_USER": "tracker",
    "POSTGRES_PASSWORD": "x",
    "POSTGRES_HOST": "db",
}


def load_prod(monkeypatch, **extra):
    for key, value in {**PROD_ENV, **extra}.items():
        monkeypatch.setenv(key, value)
    import config.settings.prod as prod

    return importlib.reload(prod)


def test_dev_settings_use_dev_database():
    # Разработка и тесты никогда не трогают рабочую базу `tracker`.
    assert settings.DATABASES["default"]["NAME"].endswith("tracker_dev")


@pytest.mark.parametrize(("flag", "expected"), [("0", False), ("1", True)])
def test_prod_https_flags_follow_env(monkeypatch, flag, expected):
    prod = load_prod(monkeypatch, DJANGO_HTTPS=flag)
    assert prod.SESSION_COOKIE_SECURE is expected
    assert prod.CSRF_COOKIE_SECURE is expected
    assert prod.SECURE_SSL_REDIRECT is expected


def test_prod_uses_whitenoise(monkeypatch):
    prod = load_prod(monkeypatch)
    assert "whitenoise.middleware.WhiteNoiseMiddleware" in prod.MIDDLEWARE
