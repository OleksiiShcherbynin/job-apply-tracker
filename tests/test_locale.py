import pytest
from django.conf import settings
from django.urls import reverse

from accounts.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def logged_in(client):
    client.force_login(UserFactory())
    return client


def test_english_by_default_even_if_browser_prefers_slovak(logged_in):
    response = logged_in.get(reverse("tracker:dashboard"), HTTP_ACCEPT_LANGUAGE="sk")

    assert '<html lang="en"' in response.text


def test_cookie_picks_the_language(logged_in):
    logged_in.cookies[settings.LANGUAGE_COOKIE_NAME] = "ru"

    response = logged_in.get(reverse("tracker:dashboard"))

    assert '<html lang="ru"' in response.text


@pytest.mark.parametrize("value", ["de", '"><script>', ""])
def test_unsupported_cookie_falls_back_to_english(logged_in, value):
    logged_in.cookies[settings.LANGUAGE_COOKIE_NAME] = value

    response = logged_in.get(reverse("tracker:dashboard"))

    assert response.status_code == 200
    assert '<html lang="en"' in response.text


def test_set_language_sets_cookie_and_returns(logged_in):
    response = logged_in.post(reverse("set_language"), {"language": "sk", "next": "/inbox/"})

    assert response.status_code == 302
    assert response["Location"] == "/inbox/"
    assert response.cookies[settings.LANGUAGE_COOKIE_NAME].value == "sk"


def test_language_choice_survives_closing_the_browser(logged_in):
    response = logged_in.post(reverse("set_language"), {"language": "ru", "next": "/"})

    # A cookie without max-age dies with the browser session.
    assert response.cookies[settings.LANGUAGE_COOKIE_NAME]["max-age"] >= 60 * 60 * 24 * 365


def test_set_language_never_redirects_off_site(logged_in):
    response = logged_in.post(
        reverse("set_language"), {"language": "sk", "next": "https://evil.example/"}
    )

    assert "evil.example" not in response["Location"]
